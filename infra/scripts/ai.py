#!/usr/bin/env python3
"""Opt-in AI deployment/teardown; no AWS operations occur at import time."""

import argparse
import json
import math
import os
import re
import sys

import deploy as base

AI_REGION = "us-east-1"
AI_ENV = {**base.ENV, "AWS_REGION": AI_REGION, "AWS_DEFAULT_REGION": AI_REGION}
DEFAULT_MODEL = "us.amazon.nova-micro-v1:0"


def deployed_backend_sha():
    values = base.outputs("backend")  # Existing ECS/auth stacks remain eu-north-1.
    definition = base.aws(
        "ecs",
        "describe-task-definition",
        "--task-definition",
        values["TaskDefinitionArn"],
    )["taskDefinition"]
    containers = [
        c for c in definition["containerDefinitions"] if c["name"] == "backend"
    ]
    image = containers[0]["image"] if len(containers) == 1 else ""
    match = re.fullmatch(
        rf"{base.ACCOUNT}\.dkr\.ecr\.{base.REGION}\.amazonaws\.com/"
        r"spry-backend:([a-f0-9]{40})",
        image,
    )
    if not match:
        raise RuntimeError(
            "Backend task definition must reference an immutable full-SHA image"
        )
    return match.group(1)


def repository(name, region):
    uri = base.outputs(f"{name}-ecr", region=region)["RepositoryUri"]
    expected = f"{base.ACCOUNT}.dkr.ecr.{region}.amazonaws.com/spry-{name}"
    if uri != expected:
        raise RuntimeError("Unexpected ECR repository; refusing image operations")
    return uri


def image_exists(uri, sha, region):
    images = base.aws(
        "ecr", "list-images", "--repository-name", uri.split("/", 1)[1], region=region
    )["imageIds"]
    return any(image.get("imageTag") == sha for image in images)


def docker_login(uri, region):
    password = base.aws("ecr", "get-login-password", text=True, region=region)
    base.execute(
        ["docker", "login", "--username", "AWS", "--password-stdin", uri.split("/")[0]],
        input=password + "\n",
        capture=True,
        env=AI_ENV,
    )


def lambda_image(sha, source, reports_repository):
    """Copy the reports Lambda image, never the ECS/Uvicorn image."""
    base.deploy_stack("ai-ecr", "ai-ecr.yml", {}, region=AI_REGION)
    target = repository("ai", AI_REGION)
    image = f"{target}:{sha}"
    if image_exists(target, sha, AI_REGION):
        return image
    base.guard()
    docker_login(target, AI_REGION)
    if image_exists(reports_repository, sha, base.REGION):
        docker_login(reports_repository, base.REGION)
        original = f"{reports_repository}:{sha}"
        base.execute(
            ["docker", "pull", "--platform", "linux/arm64", original], env=AI_ENV
        )
        base.execute(["docker", "tag", original, image], env=AI_ENV)
        base.execute(["docker", "push", image], env=AI_ENV)
        print("Copied reports Lambda image at backend SHA; ECS image was not used.")
    else:
        base.execute(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                "linux/arm64",
                "--provenance=false",
                "--push",
                "--tag",
                image,
                "--file",
                str(source / "back/Dockerfile.lambda"),
                str(source / "back"),
            ],
            env=AI_ENV,
        )
        print(
            "Built reports-compatible Lambda image from deployed backend SHA; not ECS image."
        )
    return image


def deploy(model, input_price, output_price):
    base.guard()
    base.revision()  # Clean committed tree, including templates/tooling.
    if not re.fullmatch(
        r"us\.(amazon\.nova-[a-z0-9.:-]+|anthropic\.claude-[a-z0-9.:-]+)", model
    ):
        raise RuntimeError(
            "Use an explicit US Nova/Claude cross-region inference profile ID"
        )
    if not all(
        math.isfinite(price) and price >= 0 for price in (input_price, output_price)
    ):
        raise RuntimeError("Token prices must be finite and nonnegative")
    authentication = base.auth_values()
    site = base.outputs("frontend")["SiteUrl"]
    if not re.fullmatch(r"https://[a-z0-9]+\.cloudfront\.net", site):
        raise RuntimeError("Unexpected exact frontend origin")
    sha = deployed_backend_sha()
    reports_repository = repository("reports", base.REGION)
    with base.source_snapshot(sha) as source:
        if not (source / "back/app/ai/agenda_lambda.py").is_file():
            raise RuntimeError(
                "Deploy the backend commit containing the agenda handler first"
            )
        if not (source / "back/Dockerfile.lambda").is_file():
            raise RuntimeError(
                "Deployed backend SHA lacks the Lambda-compatible Dockerfile"
            )
        image = lambda_image(sha, source, reports_repository)
    base.deploy_stack(
        "ai",
        "ai.yml",
        {
            "ImageUri": image,
            "CognitoIssuer": authentication["CognitoIssuer"],
            "CognitoClientId": authentication["CognitoClientId"],
            "SiteOrigin": site,
            "ParserModel": model,
            "ParserInputPricePerMillion": input_price,
            "ParserOutputPricePerMillion": output_price,
        },
        region=AI_REGION,
    )
    values = base.outputs("ai", region=AI_REGION)
    base.save_manifest(
        {
            "ai_region": AI_REGION,
            "ai_backend_sha": sha,
            "ai_image": image,
            "parser_url": values["ParserUrl"],
            "parser_model": model,
        }
    )
    base.guard()
    print(
        f"Parser: {values['ParserUrl']} ({AI_REGION}); application validates Cognito tokens."
    )
    print("$5 monthly account-wide budget is an email alert, NOT a spending cap.")


def destroy(confirmed=False):
    if not confirmed and os.environ.get("SPRY_CONFIRM_DESTROY_AI") != "spry-ai":
        raise RuntimeError(
            "AI-only teardown requires --confirm-destroy-ai or SPRY_CONFIRM_DESTROY_AI=spry-ai"
        )
    base.guard()
    base.revision()
    # Hard-coded allowlist: never delete base/backend/auth/reports resources.
    base.aws(
        "cloudformation", "delete-stack", "--stack-name", "spry-ai", region=AI_REGION
    )
    base.execute(
        [
            "aws",
            "cloudformation",
            "wait",
            "stack-delete-complete",
            "--stack-name",
            "spry-ai",
            "--region",
            AI_REGION,
        ],
        env=AI_ENV,
    )
    base.guard()
    # Empty ONLY this repository; CloudFormation then removes the repository.
    images = base.aws(
        "ecr", "list-images", "--repository-name", "spry-ai", region=AI_REGION
    )["imageIds"]
    for start in range(0, len(images), 100):
        result = base.aws(
            "ecr",
            "batch-delete-image",
            "--repository-name",
            "spry-ai",
            "--image-ids",
            json.dumps(images[start : start + 100]),
            region=AI_REGION,
        )
        if result.get("failures"):
            raise RuntimeError(
                "Could not remove AI images; ECR stack retained for explicit recovery"
            )
    base.aws(
        "cloudformation",
        "delete-stack",
        "--stack-name",
        "spry-ai-ecr",
        region=AI_REGION,
    )
    base.execute(
        [
            "aws",
            "cloudformation",
            "wait",
            "stack-delete-complete",
            "--stack-name",
            "spry-ai-ecr",
            "--region",
            AI_REGION,
        ],
        env=AI_ENV,
    )
    print("Deleted only spry-ai and spry-ai-ecr (including AI images/logs/budget).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["deploy", "destroy"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input-price", type=float, default=0.035)
    parser.add_argument("--output-price", type=float, default=0.14)
    parser.add_argument("--confirm-destroy-ai", action="store_true")
    arguments = parser.parse_args()
    with base.deployment_lock():
        if arguments.target == "deploy":
            deploy(arguments.model, arguments.input_price, arguments.output_price)
        else:
            destroy(arguments.confirm_destroy_ai)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, KeyError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
