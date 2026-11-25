"""Offline AI infrastructure tests; every AWS/Docker deployment call is mocked."""

import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

INFRA = Path(__file__).parents[1]
sys.path.insert(0, str(INFRA / "scripts"))
SPEC = importlib.util.spec_from_file_location("ai", INFRA / "scripts/ai.py")
ai = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ai)
sys.path.pop(0)
base = ai.base
SHA = "a" * 40
REPORTS = f"{base.ACCOUNT}.dkr.ecr.{base.REGION}.amazonaws.com/spry-reports"
TARGET = f"{base.ACCOUNT}.dkr.ecr.{ai.AI_REGION}.amazonaws.com/spry-ai"


class AiTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (INFRA / "ai.yml").read_text()

    def test_small_arm_lambda_without_vpc_or_database(self):
        for expected in [
            "Architectures: [arm64]",
            "PackageType: Image",
            "Timeout: 30",
            "MemorySize: 512",
            "ReservedConcurrentExecutions: 2",
            "RetentionInDays: 14",
            "Command: [app.ai.agenda_lambda.handler]",
        ]:
            self.assertIn(expected, self.template)
        for forbidden in [
            "VpcConfig",
            "DATABASE_URL",
            "AWS::RDS",
            "AWS::EC2",
            "secretsmanager:",
        ]:
            self.assertNotIn(forbidden, self.template)

    def test_invoke_only_selected_profile_and_foundation_models(self):
        self.assertIn("AWSLambdaBasicExecutionRole", self.template)
        self.assertEqual(self.template.count("Action: bedrock:InvokeModel"), 2)
        self.assertIn("inference-profile/${ParserModel}", self.template)
        self.assertIn("foundation-model/${FoundationModel}", self.template)
        self.assertIn("bedrock:InferenceProfileArn:", self.template)
        for forbidden in [
            "bedrock:*",
            "CreateInference",
            "aws-marketplace",
            "Resource: '*'",
            'Resource: "*"',
        ]:
            self.assertNotIn(forbidden, self.template)

    def test_exact_origin_and_both_public_url_permissions(self):
        cors = self.template.split("      Cors:\n", 1)[1].split(
            "  ParserUrlPermission:", 1
        )[0]
        self.assertIn("AllowOrigins: [!Ref SiteOrigin]", cors)
        self.assertIn("AllowMethods: [POST]", cors)
        self.assertIn("AllowHeaders: [Authorization, Content-Type]", cors)
        self.assertNotIn("*", cors)
        self.assertIn("'https://[a-z0-9]+\\.cloudfront\\.net'", self.template)
        self.assertIn("Action: lambda:InvokeFunctionUrl", self.template)
        self.assertIn("FunctionUrlAuthType: NONE", self.template)
        self.assertIn("Action: lambda:InvokeFunction\n", self.template)
        self.assertIn("InvokedViaFunctionUrl: true", self.template)
        self.assertEqual(self.template.count("Principal: '*'"), 2)

    def test_public_config_and_alert_not_cap(self):
        self.assertIn("Default: us.amazon.nova-micro-v1:0", self.template)
        self.assertIn("Default: 0.035", self.template)
        self.assertIn("Default: 0.14", self.template)
        for key in [
            "PARSER_MODEL",
            "PARSER_INPUT_PRICE_PER_MILLION",
            "PARSER_OUTPUT_PRICE_PER_MILLION",
            "COGNITO_ISSUER",
            "COGNITO_CLIENT_ID",
        ]:
            self.assertIn(key + ": !Ref", self.template)
        for forbidden in [
            "AWS_ACCESS_KEY",
            "AWS_SECRET_ACCESS",
            "GoogleClientSecret",
            "BudgetAction",
            "CostFilters:",
        ]:
            self.assertNotIn(forbidden, self.template)
        for expected in [
            "BudgetType: COST",
            "TimeUnit: MONTHLY",
            "Amount: 5, Unit: USD",
            "mandzyuk.pn@ucu.edu.ua",
            "not a spending cap",
        ]:
            self.assertIn(expected, self.template)
        self.assertIn("ParserFunctionName:", self.template)

    def test_ecr_immutable_and_dedicated(self):
        template = (INFRA / "ai-ecr.yml").read_text()
        self.assertIn("RepositoryName: spry-ai", template)
        self.assertIn("ImageTagMutability: IMMUTABLE", template)
        self.assertIn("EncryptionType: AES256", template)
        self.assertNotIn("spry-reports", template)


class AiToolingTests(unittest.TestCase):
    def test_region_defaults_and_explicit_ai_override(self):
        with patch.object(base, "execute", return_value="{}") as execute:
            base.aws("sts", "get-caller-identity")
            self.assertIn("eu-north-1", execute.call_args.args[0])
            base.aws("cloudformation", "describe-stacks", region=ai.AI_REGION)
            self.assertIn("us-east-1", execute.call_args.args[0])
        self.assertEqual(base.REGION, "eu-north-1")
        self.assertEqual(ai.AI_ENV["AWS_DEFAULT_REGION"], "us-east-1")
        self.assertEqual(ai.AI_ENV["AWS_REGION"], "us-east-1")

    def test_backend_sha_from_existing_task_definition_not_local_head(self):
        with (
            patch.object(
                base, "outputs", return_value={"TaskDefinitionArn": "existing-task"}
            ) as outputs,
            patch.object(
                base,
                "aws",
                return_value={
                    "taskDefinition": {
                        "containerDefinitions": [
                            {
                                "name": "backend",
                                "image": f"{base.ACCOUNT}.dkr.ecr.eu-north-1.amazonaws.com/spry-backend:{SHA}",
                            }
                        ]
                    }
                },
            ) as aws,
        ):
            self.assertEqual(ai.deployed_backend_sha(), SHA)
            outputs.assert_called_once_with("backend")
            self.assertIn("existing-task", aws.call_args.args)

    def test_backend_requires_expected_repo_and_full_sha(self):
        for image in ["evil/image:" + SHA, TARGET + ":" + SHA, "backend:latest"]:
            with (
                patch.object(
                    base, "outputs", return_value={"TaskDefinitionArn": "task"}
                ),
                patch.object(
                    base,
                    "aws",
                    return_value={
                        "taskDefinition": {
                            "containerDefinitions": [
                                {"name": "backend", "image": image}
                            ]
                        }
                    },
                ),
                self.assertRaisesRegex(RuntimeError, "immutable full-SHA"),
            ):
                ai.deployed_backend_sha()

    def test_copy_uses_reports_lambda_image_and_separate_regions(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(base, "deploy_stack") as stack,
            patch.object(ai, "repository", return_value=TARGET),
            patch.object(ai, "image_exists", side_effect=[False, True]) as exists,
            patch.object(base, "guard") as guard,
            patch.object(ai, "docker_login") as login,
            patch.object(base, "execute") as execute,
        ):
            image = ai.lambda_image(SHA, Path(directory), REPORTS)
            stack.assert_called_once_with(
                "ai-ecr", "ai-ecr.yml", {}, region="us-east-1"
            )
            self.assertEqual(
                exists.call_args_list[1].args, (REPORTS, SHA, "eu-north-1")
            )
            self.assertEqual(login.call_args_list[0].args, (TARGET, "us-east-1"))
            self.assertEqual(login.call_args_list[1].args, (REPORTS, "eu-north-1"))
            commands = [call.args[0] for call in execute.call_args_list]
            self.assertEqual(
                commands[0],
                ["docker", "pull", "--platform", "linux/arm64", f"{REPORTS}:{SHA}"],
            )
            self.assertEqual(commands[-1], ["docker", "push", image])
            self.assertNotIn("spry-backend", json.dumps(commands))
            guard.assert_called_once()

    def test_missing_reports_tag_builds_lambda_dockerfile_from_snapshot(self):
        with (
            patch.object(base, "deploy_stack"),
            patch.object(ai, "repository", return_value=TARGET),
            patch.object(ai, "image_exists", side_effect=[False, False]),
            patch.object(base, "guard"),
            patch.object(ai, "docker_login"),
            patch.object(base, "execute") as execute,
        ):
            ai.lambda_image(SHA, Path("/exact-committed-snapshot"), REPORTS)
            command = execute.call_args.args[0]
            self.assertIn("/exact-committed-snapshot/back/Dockerfile.lambda", command)
            self.assertIn("linux/arm64", command)
            self.assertIn("--provenance=false", command)
            self.assertIn(f"{TARGET}:{SHA}", command)

    def test_deploy_reuses_guards_clean_revision_and_exact_backend_snapshot(self):
        events = []
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "back/app/ai").mkdir(parents=True)
            (source / "back/app/ai/agenda_lambda.py").touch()
            (source / "back/Dockerfile.lambda").touch()

            @contextmanager
            def snapshot(sha):
                self.assertEqual(sha, SHA)
                yield source

            def outputs(name, **kwargs):
                if name == "frontend":
                    self.assertFalse(kwargs)
                    return {"SiteUrl": "https://example.cloudfront.net"}
                self.assertEqual((name, kwargs), ("ai", {"region": "us-east-1"}))
                return {"ParserUrl": "https://example.lambda-url.us-east-1.on.aws/"}

            with (
                patch.object(base, "guard", side_effect=lambda: events.append("guard")),
                patch.object(
                    base, "revision", side_effect=lambda: events.append("revision")
                ),
                patch.object(
                    base,
                    "auth_values",
                    return_value={
                        "CognitoIssuer": "public-issuer",
                        "CognitoClientId": "public-client",
                    },
                ),
                patch.object(base, "outputs", side_effect=outputs),
                patch.object(ai, "deployed_backend_sha", return_value=SHA),
                patch.object(ai, "repository", return_value=REPORTS),
                patch.object(base, "source_snapshot", side_effect=snapshot),
                patch.object(ai, "lambda_image", return_value=f"{TARGET}:{SHA}"),
                patch.object(base, "deploy_stack") as stack,
                patch.object(base, "save_manifest") as manifest,
            ):
                ai.deploy(ai.DEFAULT_MODEL, 0.035, 0.14)
                self.assertEqual(events, ["guard", "revision", "guard"])
                self.assertEqual(stack.call_args.kwargs, {"region": "us-east-1"})
                parameters = stack.call_args.args[2]
                self.assertEqual(
                    parameters["SiteOrigin"], "https://example.cloudfront.net"
                )
                self.assertEqual(parameters["CognitoClientId"], "public-client")
                self.assertNotIn("secret", json.dumps(manifest.call_args.args).lower())

    def test_existing_ai_image_is_not_overwritten(self):
        with (
            patch.object(base, "deploy_stack"),
            patch.object(ai, "repository", return_value=TARGET),
            patch.object(ai, "image_exists", return_value=True),
            patch.object(base, "execute") as execute,
        ):
            ai.lambda_image(SHA, Path("/unused"), REPORTS)
            execute.assert_not_called()

    def test_destroy_requires_explicit_confirmation_before_any_aws_call(self):
        with (
            patch.dict(ai.os.environ, {"SPRY_CONFIRM_DESTROY_AI": ""}),
            patch.object(base, "guard") as guard,
            patch.object(base, "aws") as aws,
            self.assertRaisesRegex(RuntimeError, "requires"),
        ):
            ai.destroy()
        guard.assert_not_called()
        aws.assert_not_called()

    def test_destroy_writes_are_allowlisted_and_always_us_east(self):
        def aws(*args, **kwargs):
            self.assertEqual(kwargs, {"region": "us-east-1"})
            if args[0] == "cloudformation":
                self.assertIn(args[3], ["spry-ai", "spry-ai-ecr"])
            else:
                self.assertEqual(args[3], "spry-ai")
            return {"imageIds": [{"imageTag": SHA}]}

        with (
            patch.object(base, "guard") as guard,
            patch.object(base, "revision") as revision,
            patch.object(base, "aws", side_effect=aws) as calls,
            patch.object(base, "execute") as execute,
        ):
            ai.destroy(confirmed=True)
            self.assertEqual(guard.call_count, 2)
            revision.assert_called_once()
            self.assertEqual(calls.call_count, 4)
            self.assertEqual(execute.call_count, 2)
            for call in execute.call_args_list:
                self.assertIn("us-east-1", call.args[0])

    def test_frontend_parser_stack_missing_fails_clearly(self):
        with (
            patch.object(base, "outputs", side_effect=RuntimeError("missing")),
            self.assertRaisesRegex(RuntimeError, "deploy-ai first"),
        ):
            base.parser_url()

    def test_frontend_parser_url_is_trusted_and_region_explicit(self):
        url = "https://example.lambda-url.us-east-1.on.aws/"
        with patch.object(base, "outputs", return_value={"ParserUrl": url}) as outputs:
            self.assertEqual(base.parser_url(), url)
            outputs.assert_called_once_with("ai", region="us-east-1")
        for invalid in [
            "https://evil.example/",
            "https://example.lambda-url.eu-north-1.on.aws/",
        ]:
            with (
                patch.object(base, "outputs", return_value={"ParserUrl": invalid}),
                self.assertRaisesRegex(RuntimeError, "Invalid AI parser URL"),
            ):
                base.parser_url()
        source = (INFRA / "scripts/deploy.py").read_text()
        self.assertIn('f"VITE_PARSER_URL={parser_endpoint}"', source)

    def test_wrappers_use_shared_private_lock_entrypoint(self):
        source = (INFRA / "scripts/ai.py").read_text()
        self.assertIn("with base.deployment_lock():", source)
        for target in ["deploy", "destroy"]:
            wrapper = (INFRA.parent / f"scripts/{target}-ai.sh").read_text()
            self.assertIn(f'"$ROOT/infra/scripts/ai.py" {target} "$@"', wrapper)
            self.assertNotIn("aws ", wrapper)


if __name__ == "__main__":
    unittest.main()
