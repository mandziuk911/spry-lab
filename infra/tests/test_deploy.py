"""Safety gate tests: no network access, real credentials or cloud mutations."""

import importlib.util
import json
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

    def auth_outputs(self):
        return {
            "UserPoolId": "eu-north-1_TestPool",
            "CognitoIssuer": "https://cognito-idp.eu-north-1.amazonaws.com/eu-north-1_TestPool",
            "CognitoClientId": "123exampleclient",
            "CognitoDomain": f"https://{deploy.AUTH_PREFIX}.auth.eu-north-1.amazoncognito.com",
            "LoginUrl": "https://example.cloudfront.net/login/",
        }

    def test_auth_outputs_reject_untrusted_issuer_and_domain(self):
        for key, value in [
            ("CognitoIssuer", "https://attacker.example/pool"),
            ("CognitoDomain", "https://attacker.example"),
            ("CognitoClientId", ""),
        ]:
            values = {**self.auth_outputs(), key: value}
            with (
                patch.object(deploy, "outputs", return_value=values),
                self.assertRaises(RuntimeError),
            ):
                deploy.auth_values()

    def test_local_configuration_contains_only_public_auth_values(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deploy, "ROOT", Path(temporary)),
            patch.object(deploy, "guard"),
            patch.object(deploy, "auth_values", return_value=self.auth_outputs()),
        ):
            path = deploy.ROOT / ".env"
            path.write_text("POSTGRES_DB=existing\nCOGNITO_CLIENT_ID=old\n")
            deploy.local_auth()
            deploy.local_auth()
            text = path.read_text()
            self.assertIn("POSTGRES_DB=existing", text)
            self.assertEqual(text.count("COGNITO_CLIENT_ID="), 1)
            self.assertIn("COGNITO_CLIENT_ID=123exampleclient", text)
            self.assertNotIn("client_secret", text)
            self.assertNotIn("AWS_ACCESS_KEY", text)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_auth_rejects_public_secret_file_before_provisioning(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deploy, "STATE", Path(temporary)),
            patch.object(deploy, "guard"),
            patch.object(deploy, "revision", return_value="a" * 40),
            patch.object(
                deploy,
                "outputs",
                return_value={"SiteUrl": "https://example.cloudfront.net"},
            ),
            patch.object(deploy, "deploy_stack") as provision,
        ):
            path = deploy.STATE / "google-oauth.json"
            path.write_text("{}")
            path.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "permissions 0600"):
                deploy.auth()
            provision.assert_not_called()

    def test_auth_rejects_wrong_google_redirect_without_provisioning(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deploy, "STATE", Path(temporary)),
            patch.object(deploy, "guard"),
            patch.object(deploy, "revision", return_value="a" * 40),
            patch.object(
                deploy,
                "outputs",
                return_value={"SiteUrl": "https://example.cloudfront.net"},
            ),
            patch.object(deploy, "deploy_stack") as provision,
        ):
            path = deploy.STATE / "google-oauth.json"
            path.write_text(
                json.dumps(
                    {
                        "web": {
                            "client_id": "123-demo.apps.googleusercontent.com",
                            "client_secret": "PRIVATE_FAKE_SECRET",
                            "redirect_uris": ["https://attacker.example/callback"],
                        }
                    }
                )
            )
            path.chmod(0o600)
            with self.assertRaisesRegex(RuntimeError, "exact Cognito redirect"):
                deploy.auth()
            provision.assert_not_called()

    def test_auth_secret_is_only_passed_to_noecho_parameter(self):
        secret = "PRIVATE_FAKE_SECRET"
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deploy, "STATE", Path(temporary)),
            patch.object(deploy, "guard"),
            patch.object(deploy, "revision", return_value="a" * 40),
            patch.object(
                deploy,
                "outputs",
                return_value={"SiteUrl": "https://example.cloudfront.net"},
            ),
            patch.object(deploy, "auth_values", return_value=self.auth_outputs()),
            patch.object(deploy, "deploy_stack") as provision,
        ):
            path = deploy.STATE / "google-oauth.json"
            path.write_text(
                json.dumps(
                    {
                        "web": {
                            "client_id": "123-demo.apps.googleusercontent.com",
                            "client_secret": secret,
                            "redirect_uris": [
                                f"https://{deploy.AUTH_PREFIX}.auth.eu-north-1.amazoncognito.com/oauth2/idpresponse"
                            ],
                        }
                    }
                )
            )
            path.chmod(0o600)
            deploy.auth()
            self.assertEqual(provision.call_args.args[2]["GoogleClientSecret"], secret)
            manifest = (deploy.STATE / "deployment.json").read_text()
            self.assertNotIn(secret, manifest)
            self.assertNotIn("client_secret", manifest)


if __name__ == "__main__":
    unittest.main()
