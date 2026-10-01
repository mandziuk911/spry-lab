#!/usr/bin/env python3
"""Free-plan-only lab deployment. Credentials come from aws login, never .env."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "673478369996"
REGION = "eu-north-1"
PROJECT = "spry"
STATE = Path.home() / ".local" / "state" / "spry-aws"
ENV = {
    **os.environ,
    "AWS_REGION": REGION,
    "AWS_DEFAULT_REGION": REGION,
    "AWS_PAGER": "",
}
if not ENV.get("AWS_PROFILE"):
    ENV.pop("AWS_PROFILE", None)
    if not (ENV.get("AWS_ACCESS_KEY_ID") and ENV.get("AWS_SESSION_TOKEN")):
        ENV["AWS_PROFILE"] = "spry"


def execute(command, *, capture=False, input=None, env=None):
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env or ENV,
        text=True,
        input=input,
        stdout=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode:
        # Do not stringify commands: parameters and stdin can contain secrets.
        raise RuntimeError(
            f"{command[0]} failed (exit {result.returncode}); deployment stopped"
        )
    return result.stdout.strip() if capture else ""


def aws(*arguments, text=False):
    result = execute(
        ["aws", *arguments, "--output", "text" if text else "json"], capture=True
    )
    return result if text else json.loads(result)


def guard():
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != ACCOUNT:
        raise RuntimeError("Unexpected AWS account; refusing deployment")
    if not identity["Arn"].startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/"):
        raise RuntimeError(
            "Temporary assumed-role credentials required; no root or IAM user keys"
        )
    plan = aws("freetier", "get-account-plan-state")
    if plan["accountPlanType"] != "FREE" or plan["accountPlanStatus"] != "ACTIVE":
        raise RuntimeError(
            "An ACTIVE Free account is required; no paid-plan deployment allowed"
        )
    credits = float(plan["accountPlanRemainingCredits"]["amount"])
    if credits < 20:
        raise RuntimeError(
            "Less than $20 credits remain; refusing additional deployment"
        )
    print(
        f"Verified Free plan in {ACCOUNT}/{REGION}; ${credits:.2f} credits remain",
        flush=True,
    )


def revision():
    execute(["git", "diff", "--exit-code", "HEAD"], capture=True)
    if execute(["git", "ls-files", "--others", "--exclude-standard"], capture=True):
        raise RuntimeError("Commit or remove untracked files before deployment")
    return execute(["git", "rev-parse", "HEAD"], capture=True)


@contextmanager
def deployment_lock():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    with (STATE / "deployment.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another deployment is already running") from error
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def source_snapshot(sha):
    with tempfile.TemporaryDirectory(prefix="spry-source-") as directory:
        archive = Path(directory) / "source.tar"
        source = Path(directory) / "source"
        execute(["git", "archive", "--format=tar", f"--output={archive}", sha])
        source.mkdir()
        with tarfile.open(archive) as contents:
            contents.extractall(source, filter="data")
        yield source


def token():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    arn = outputs("backend-ecr")["OriginTokenSecretArn"]
    value = aws("secretsmanager", "get-secret-value", "--secret-id", arn)[
        "SecretString"
    ]
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError("Invalid origin token; refusing deployment")
    path = STATE / "origin-token"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(value)
    return value


def stack(name):
    return aws(
        "cloudformation", "describe-stacks", "--stack-name", f"{PROJECT}-{name}"
    )["Stacks"][0]


def outputs(name):
    return {
        item["OutputKey"]: item["OutputValue"]
        for item in stack(name).get("Outputs", [])
    }


def deploy_stack(name, template, parameters):
    guard()
    print(f"Deploying {PROJECT}-{name} (no destructive rollback cleanup)", flush=True)
    with tempfile.TemporaryDirectory(prefix="spry-parameters-") as directory:
        path = Path(directory) / "parameters.json"
        path.write_text(
            json.dumps(
                [
                    {"ParameterKey": key, "ParameterValue": str(value)}
                    for key, value in parameters.items()
                ]
            )
        )
        path.chmod(0o600)
        template_path = Path(directory) / "template.yaml"
        template_path.write_text(
            execute(["git", "show", f"HEAD:infra/{template}"], capture=True)
        )
        execute(
            [
                "aws",
                "cloudformation",
                "deploy",
                "--stack-name",
                f"{PROJECT}-{name}",
                "--template-file",
                str(template_path),
                "--parameter-overrides",
                f"file://{path}",
                "--capabilities",
                "CAPABILITY_IAM",
                "--tags",
                "Project=spry",
                "--no-fail-on-empty-changeset",
            ]
        )


def prefix_list():
    items = aws(
        "ec2",
        "describe-managed-prefix-lists",
        "--filters",
        "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing",
    )["PrefixLists"]
    if len(items) != 1:
        raise RuntimeError(
            "Cannot uniquely identify the CloudFront origin-facing prefix list"
        )
    return items[0]["PrefixListId"]


def backend():
    guard()
    sha = revision()
    deploy_stack("backend-ecr", "backend-ecr.yaml", {"ProjectName": PROJECT})
    repository = outputs("backend-ecr")["RepositoryUri"]
    image = f"{repository}:{sha}"
    existing = aws(
        "ecr", "list-images", "--repository-name", repository.split("/", 1)[1]
    )["imageIds"]
    if not any(item.get("imageTag") == sha for item in existing):
        password = aws("ecr", "get-login-password", text=True)
        execute(
            [
                "docker",
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                repository.split("/")[0],
            ],
            input=password,
        )
        with source_snapshot(sha) as source:
            execute(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--platform",
                    "linux/arm64",
                    "--provenance=false",
                    "--tag",
                    image,
                    "--push",
                    str(source / "back"),
                ]
            )
    parameters = {
        "ProjectName": PROJECT,
        "ImageUri": image,
        "DesiredCount": 0,
        "OriginToken": token(),
        "CloudFrontPrefixListId": prefix_list(),
    }
    # Demo deployments intentionally pause the service while migrating. A failure
    # retains database/resources and leaves serving disabled for explicit recovery.
    deploy_stack("backend", "backend.yaml", parameters)
    values = outputs("backend")
    network = {
        "awsvpcConfiguration": {
            "subnets": values["PublicSubnetIds"].split(","),
            "securityGroups": [values["TaskSecurityGroupId"]],
            "assignPublicIp": "ENABLED",
        }
    }
    overrides = {
        "containerOverrides": [
            {
                "name": "backend",
                "command": ["uv", "run", "--no-sync", "alembic", "upgrade", "head"],
            }
        ]
    }
    started = aws(
        "ecs",
        "run-task",
        "--cluster",
        values["ClusterName"],
        "--task-definition",
        values["TaskDefinitionArn"],
        "--launch-type",
        "FARGATE",
        "--network-configuration",
        json.dumps(network),
        "--overrides",
        json.dumps(overrides),
        "--count",
        "1",
        "--started-by",
        "spry-migration",
    )
    if started.get("failures") or len(started.get("tasks", [])) != 1:
        raise RuntimeError(
            "Migration task could not be started; service remains disabled"
        )
    task = started["tasks"][0]["taskArn"]
    print("Waiting for controlled migration task", flush=True)
    execute(
        [
            "aws",
            "ecs",
            "wait",
            "tasks-stopped",
            "--cluster",
            values["ClusterName"],
            "--tasks",
            task,
        ]
    )
    stopped = aws(
        "ecs", "describe-tasks", "--cluster", values["ClusterName"], "--tasks", task
    )["tasks"][0]
    container = next(
        item for item in stopped["containers"] if item["name"] == "backend"
    )
    if container.get("exitCode") != 0:
        raise RuntimeError(
            "Migration failed; service remains disabled. Inspect /ecs/spry-backend logs"
        )
    parameters["DesiredCount"] = 1
    deploy_stack("backend", "backend.yaml", parameters)
    execute(
        [
            "aws",
            "ecs",
            "wait",
            "services-stable",
            "--cluster",
            values["ClusterName"],
            "--services",
            values["ServiceName"],
        ]
    )
    services = aws(
        "ecs",
        "describe-services",
        "--cluster",
        values["ClusterName"],
        "--services",
        values["ServiceName"],
    )["services"]
    if not services or services[0]["runningCount"] < 1:
        raise RuntimeError("Backend has no healthy running task")
    save_manifest({"backend_image": image, "backend_sha": sha})
    guard()
    print("Backend deployed; public access is through CloudFront only", flush=True)


def save_manifest(values):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = STATE / "deployment.json"
    current = json.loads(path.read_text()) if path.exists() else {}
    current.update({"account": ACCOUNT, "region": REGION, **values})
    path.write_text(json.dumps(current, indent=2) + "\n")
    path.chmod(0o600)


def frontend():
    guard()
    sha = revision()
    backend_values = outputs("backend")
    deploy_stack(
        "frontend",
        "frontend.yaml",
        {
            "ProjectName": PROJECT,
            "BackendDomainName": backend_values["LoadBalancerDomainName"],
            "OriginToken": token(),
        },
    )
    values = outputs("frontend")
    with source_snapshot(sha) as source:
        execute(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{source}:/project",
                "-v",
                "/project/front/node_modules",
                "-w",
                "/project/front",
                "-e",
                "VITE_API_URL=/",
                "node:24.0.0-bookworm-slim",
                "sh",
                "-c",
                "npm ci --no-audit --no-fund && npm run lint && npm run format:check && npm test && npm run build",
            ]
        )
        execute(
            [
                "aws",
                "s3",
                "sync",
                str(source / "front/dist"),
                f"s3://{values['BucketName']}",
                "--exclude",
                "index.html",
                "--cache-control",
                "public,max-age=31536000,immutable",
            ]
        )
        execute(
            [
                "aws",
                "s3",
                "cp",
                str(source / "front/dist/index.html"),
                f"s3://{values['BucketName']}/index.html",
                "--cache-control",
                "no-cache,no-store,must-revalidate",
                "--content-type",
                "text/html",
            ]
        )
    invalidation = aws(
        "cloudfront",
        "create-invalidation",
        "--distribution-id",
        values["DistributionId"],
        "--paths",
        "/*",
    )["Invalidation"]["Id"]
    execute(
        [
            "aws",
            "cloudfront",
            "wait",
            "invalidation-completed",
            "--distribution-id",
            values["DistributionId"],
            "--id",
            invalidation,
        ]
    )
    execute(
        [
            "aws",
            "cloudfront",
            "wait",
            "distribution-deployed",
            "--id",
            values["DistributionId"],
        ]
    )
    save_manifest(
        {
            "frontend_sha": sha,
            "site_url": values["SiteUrl"],
            "api_url": values["SiteUrl"] + "/api",
            "distribution_id": values["DistributionId"],
        }
    )
    guard()
    print(f"Frontend: {values['SiteUrl']}\nAPI: {values['SiteUrl']}/api", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["check", "backend", "frontend", "outputs"])
    target = parser.parse_args().target
    if target == "check":
        guard()
    elif target == "backend":
        with deployment_lock():
            backend()
    elif target == "frontend":
        with deployment_lock():
            frontend()
    else:
        guard()
        path = STATE / "deployment.json"
        print(path.read_text() if path.exists() else "Not deployed yet")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, KeyError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
