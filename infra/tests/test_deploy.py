"""Safety gate tests: no network access, real credentials or cloud mutations."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "deploy", Path(__file__).parents[1] / "scripts" / "deploy.py"
)
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class DeploymentSafetyTests(unittest.TestCase):
    def identity(self, account=deploy.ACCOUNT, root=False):
        return {
            "Account": account,
            "Arn": f"arn:aws:{'iam' if root else 'sts'}::{account}:"
            + ("root" if root else "assumed-role/AccountFullAccessRole/session"),
        }

    def plan(self, type="FREE", status="ACTIVE", credits=100):
        return {
            "accountPlanType": type,
            "accountPlanStatus": status,
            "accountPlanRemainingCredits": {"amount": credits, "unit": "USD"},
        }

    def test_free_plan_allowed(self):
        with patch.object(
            deploy, "aws", side_effect=[self.identity(), self.plan()]
        ) as aws:
            deploy.guard()
        self.assertEqual(aws.call_count, 2)

    def test_other_account_rejected_before_plan_request(self):
        with (
            patch.object(
                deploy, "aws", return_value=self.identity("123456789012")
            ) as aws,
            self.assertRaisesRegex(RuntimeError, "Unexpected AWS account"),
        ):
            deploy.guard()
        self.assertEqual(aws.call_count, 1)

    def test_root_credentials_rejected(self):
        with (
            patch.object(deploy, "aws", return_value=self.identity(root=True)),
            self.assertRaisesRegex(RuntimeError, "Temporary assumed-role"),
        ):
            deploy.guard()

    def test_paid_plan_rejected(self):
        with (
            patch.object(
                deploy, "aws", side_effect=[self.identity(), self.plan(type="PAID")]
            ),
            self.assertRaisesRegex(RuntimeError, "ACTIVE Free"),
        ):
            deploy.guard()

    def test_inactive_plan_rejected(self):
        with (
            patch.object(
                deploy,
                "aws",
                side_effect=[self.identity(), self.plan(status="EXPIRED")],
            ),
            self.assertRaisesRegex(RuntimeError, "ACTIVE Free"),
        ):
            deploy.guard()

    def test_insufficient_credits_rejected(self):
        with (
            patch.object(
                deploy, "aws", side_effect=[self.identity(), self.plan(credits=19.99)]
            ),
            self.assertRaisesRegex(RuntimeError, "Less than"),
        ):
            deploy.guard()

    def test_origin_secret_is_stable_and_private(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deploy, "STATE", Path(temporary) / "state"),
            patch.object(
                deploy, "outputs", return_value={"OriginTokenSecretArn": "mock-secret"}
            ),
            patch.object(deploy, "aws", return_value={"SecretString": "a" * 64}),
        ):
            first = deploy.token()
            self.assertEqual(first, deploy.token())
            self.assertEqual(len(first), 64)
            self.assertEqual(
                (deploy.STATE / "origin-token").stat().st_mode & 0o777, 0o600
            )
            self.assertEqual(deploy.STATE.stat().st_mode & 0o777, 0o700)

    def test_manifest_contains_no_origin_secret(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deploy, "STATE", Path(temporary) / "state"),
            patch.object(
                deploy, "outputs", return_value={"OriginTokenSecretArn": "mock-secret"}
            ),
            patch.object(deploy, "aws", return_value={"SecretString": "a" * 64}),
        ):
            token = deploy.token()
            deploy.save_manifest({"site_url": "https://example.cloudfront.net"})
            self.assertNotIn(token, (deploy.STATE / "deployment.json").read_text())

    def test_deployments_are_serialized(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deploy, "STATE", Path(temporary) / "state"),
        ):
            with (
                deploy.deployment_lock(),
                self.assertRaisesRegex(RuntimeError, "already running"),
                deploy.deployment_lock(),
            ):
                self.fail("Concurrent deployment acquired the lock")
            with deploy.deployment_lock():
                pass  # Lock released after the first deployment exits.

    def test_build_snapshot_uses_git_commit_without_generated_dependencies(self):
        sha = deploy.execute(["git", "rev-parse", "HEAD"], capture=True)
        expected = deploy.execute(
            ["git", "show", f"{sha}:back/app/config.py"], capture=True
        )
        with deploy.source_snapshot(sha) as source:
            self.assertEqual(
                (source / "back/app/config.py").read_text().strip(), expected
            )
            self.assertFalse((source / "front/node_modules").exists())
            self.assertFalse((source / ".env").exists())
        self.assertFalse(source.exists())

    def test_failed_commands_do_not_print_secret_arguments(self):
        secret = "DO_NOT_LOG_THIS"
        with (
            patch.object(
                deploy.subprocess,
                "run",
                return_value=deploy.subprocess.CompletedProcess([], 1),
            ),
            self.assertRaises(RuntimeError) as caught,
        ):
            deploy.execute(["aws", "command", secret])
        self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
