"""The Lambda target's infrastructure templates, read as documents.

`sam validate --lint` checks that a template is well-formed; it cannot know which
properties this deployment's security depends on. These tests pin those: the
certificate lives where CloudFront can use it, the origin is locked, no IAM
statement grants a wildcard resource, and the worker has no public URL. Each is
a claim about the parsed template, not a substring, so a comment cannot satisfy
it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

LAMBDA_DIR = Path(__file__).resolve().parents[2] / "deploy" / "lambda"


class _CloudFormationLoader(yaml.SafeLoader):
    """SafeLoader that keeps CloudFormation's short-form intrinsics as data."""


def _intrinsic(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> dict[str, Any]:
    name = "Ref" if tag_suffix == "Ref" else f"Fn::{tag_suffix}"
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {name: value}


_CloudFormationLoader.add_multi_constructor("!", _intrinsic)


def load(name: str) -> dict[str, Any]:
    return yaml.load((LAMBDA_DIR / name).read_text(), Loader=_CloudFormationLoader)


def resources_of_type(template: dict[str, Any], type_name: str) -> dict[str, Any]:
    return {
        logical_id: resource
        for logical_id, resource in template["Resources"].items()
        if resource["Type"] == type_name
    }


class TestCertificateStack:
    @pytest.fixture
    def template(self) -> dict[str, Any]:
        return load("cert.yaml")

    def test_issues_one_dns_validated_certificate_for_the_hostname(
        self, template: dict[str, Any]
    ) -> None:
        certificates = resources_of_type(template, "AWS::CertificateManager::Certificate")
        assert len(certificates) == 1
        (certificate,) = certificates.values()
        properties = certificate["Properties"]

        assert properties["ValidationMethod"] == "DNS"
        assert properties["DomainName"] == {"Ref": "DomainName"}
        assert properties["DomainValidationOptions"] == [
            {"DomainName": {"Ref": "DomainName"}, "HostedZoneId": {"Ref": "HostedZoneId"}}
        ]
        assert template["Parameters"]["DomainName"]["Default"] == "trips.botito.app"

    def test_exports_the_arn_the_application_stack_needs(self, template: dict[str, Any]) -> None:
        assert template["Outputs"]["CertificateArn"]["Value"] == {"Ref": "Certificate"}


def iam_statements(function: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        statement
        for policy in function["Properties"].get("Policies", [])
        if isinstance(policy, dict)
        for statement in policy.get("Statement", [])
    ]


class TestApplicationStack:
    @pytest.fixture
    def template(self) -> dict[str, Any]:
        return load("template.yaml")

    @pytest.fixture
    def web(self, template: dict[str, Any]) -> dict[str, Any]:
        return template["Resources"]["WebFunction"]["Properties"]

    @pytest.fixture
    def worker(self, template: dict[str, Any]) -> dict[str, Any]:
        return template["Resources"]["WorkerFunction"]["Properties"]

    def test_one_image_two_commands(self, web: dict[str, Any], worker: dict[str, Any]) -> None:
        assert web["ImageUri"] == worker["ImageUri"] == {"Ref": "ImageUri"}
        assert web["ImageConfig"]["Command"] == ["serve"]
        assert worker["ImageConfig"]["Command"] == ["worker"]

    def test_the_web_function_streams_through_a_locked_origin(
        self, template: dict[str, Any], web: dict[str, Any]
    ) -> None:
        assert web["FunctionUrlConfig"] == {"AuthType": "NONE", "InvokeMode": "RESPONSE_STREAM"}
        env = web["Environment"]["Variables"]
        assert env["AWS_LWA_INVOKE_MODE"] == "response_stream"
        assert env["ORIGIN_VERIFY_SECRET"] == {"Ref": "OriginVerifySecret"}
        assert env["CLIENT_IP_SOURCE"] == "cloudfront"

        (origin,) = template["Resources"]["Distribution"]["Properties"]["DistributionConfig"][
            "Origins"
        ]
        assert origin["OriginCustomHeaders"] == [
            {"HeaderName": "X-Origin-Verify", "HeaderValue": {"Ref": "OriginVerifySecret"}}
        ]
        assert origin["CustomOriginConfig"]["OriginProtocolPolicy"] == "https-only"

    def test_the_web_function_uses_the_pooler_without_a_client_pool(
        self, web: dict[str, Any]
    ) -> None:
        env = web["Environment"]["Variables"]
        assert env["DATABASE_URL"] == {"Ref": "DatabaseUrlPooled"}
        assert env["DB_POOL"] == "null"
        assert env["INBOX_WORKER_MODE"] == "lambda"

    def test_the_worker_has_no_url_one_instance_the_direct_endpoint_and_no_retries(
        self, template: dict[str, Any], worker: dict[str, Any]
    ) -> None:
        assert "FunctionUrlConfig" not in worker
        assert worker["ReservedConcurrentExecutions"] == 1
        assert worker["Timeout"] == 300
        assert worker["EventInvokeConfig"]["MaximumRetryAttempts"] == 0
        assert worker["Environment"]["Variables"]["DATABASE_URL"] == {"Ref": "DatabaseUrlDirect"}
        assert worker["Events"]["Drain"]["Type"] == "ScheduleV2"
        assert template["Parameters"]["WorkerSchedule"]["Default"] == "rate(6 hours)"

    def test_secrets_are_no_echo_parameters(self, template: dict[str, Any]) -> None:
        for name in (
            "DatabaseUrlPooled",
            "DatabaseUrlDirect",
            "SessionSecret",
            "OriginVerifySecret",
        ):
            assert template["Parameters"][name]["NoEcho"] is True, name

    def test_no_iam_statement_grants_a_wildcard_resource(self, template: dict[str, Any]) -> None:
        functions = resources_of_type(template, "AWS::Serverless::Function")
        for logical_id, function in functions.items():
            for statement in iam_statements(function):
                resources = statement["Resource"]
                for resource in resources if isinstance(resources, list) else [resources]:
                    assert resource != "*", f"{logical_id} grants {statement['Action']} on *"

    def test_the_web_function_may_invoke_only_the_worker(self, web: dict[str, Any]) -> None:
        (statement,) = iam_statements({"Properties": web})
        assert statement["Action"] == "lambda:InvokeFunction"
        assert str(statement["Resource"]["Fn::Sub"]).endswith(":function:${AWS::StackName}-worker")

    def test_only_hashed_assets_are_cached_at_the_edge(self, template: dict[str, Any]) -> None:
        config = template["Resources"]["Distribution"]["Properties"]["DistributionConfig"]
        caching_disabled = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
        caching_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6"

        assert config["DefaultCacheBehavior"]["CachePolicyId"] == caching_disabled
        assert config["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
        (assets,) = config["CacheBehaviors"]
        assert assets["PathPattern"] == "/assets/*"
        assert assets["CachePolicyId"] == caching_optimized


class TestInboxWiring:
    @pytest.fixture
    def template(self) -> dict[str, Any]:
        return load("template.yaml")

    def test_every_inbox_resource_is_conditional(self, template: dict[str, Any]) -> None:
        inbox = {k: v for k, v in template["Resources"].items() if k.startswith("Inbox")}
        assert inbox, "the inbox resources are missing"
        for logical_id, resource in inbox.items():
            assert resource.get("Condition") in {"HasInbox", "HasAlarmEmail"}, logical_id

    def test_the_receipt_rule_scans_and_stores_then_notifies(
        self, template: dict[str, Any]
    ) -> None:
        rule = template["Resources"]["InboxReceiptRule"]["Properties"]["Rule"]
        assert rule["ScanEnabled"] is True
        (action,) = rule["Actions"]
        assert set(action) == {"S3Action"}, "an SNS action would carry the raw MIME and bounce"
        assert action["S3Action"]["ObjectKeyPrefix"] == "inbound/"
        assert action["S3Action"]["TopicArn"] == {"Ref": "InboxTopic"}

    def test_the_bucket_is_private_encrypted_and_expires_raw_mime(
        self, template: dict[str, Any]
    ) -> None:
        bucket = template["Resources"]["InboxBucket"]["Properties"]
        assert all(bucket["PublicAccessBlockConfiguration"].values())
        assert bucket["BucketEncryption"]["ServerSideEncryptionConfiguration"]
        (rule,) = bucket["LifecycleConfiguration"]["Rules"]
        assert rule["ExpirationInDays"] == 30

    def test_object_access_is_read_and_delete_on_the_prefix_only(
        self, template: dict[str, Any]
    ) -> None:
        policy = template["Resources"]["InboxObjectAccess"]["Properties"]["PolicyDocument"]
        (statement,) = policy["Statement"]
        assert statement["Action"] == ["s3:GetObject", "s3:DeleteObject"]
        assert statement["Resource"] == {"Fn::Sub": "${InboxBucket.Arn}/inbound/*"}

    def test_the_subscription_keeps_the_signed_envelope_and_has_a_dead_letter_queue(
        self, template: dict[str, Any]
    ) -> None:
        subscription = template["Resources"]["InboxSubscription"]["Properties"]
        assert subscription["Protocol"] == "https"
        assert subscription["RawMessageDelivery"] is False
        assert subscription["Endpoint"] == {
            "Fn::Sub": "https://${DomainName}/api/v1/inbox/receipts/sns"
        }
        assert subscription["RedrivePolicy"]["deadLetterTargetArn"] == {
            "Fn::GetAtt": "InboxDeadLetterQueue.Arn"
        }

    def test_both_functions_get_the_same_inbox_configuration(
        self, template: dict[str, Any]
    ) -> None:
        web = template["Resources"]["WebFunction"]["Properties"]["Environment"]["Variables"]
        worker = template["Resources"]["WorkerFunction"]["Properties"]["Environment"]["Variables"]
        inbox_keys = {k for k in web if k.startswith("INBOX_") or k.endswith("_API_KEY")}
        assert {k: web[k] for k in inbox_keys} == {k: worker[k] for k in inbox_keys}
        assert {"INBOX_RECIPIENT", "INBOX_SNS_TOPIC_ARN", "INBOX_S3_BUCKET"} <= inbox_keys


class TestDeployScript:
    @pytest.fixture
    def script(self) -> str:
        return (LAMBDA_DIR / "deploy.sh").read_text()

    def test_is_valid_bash(self) -> None:
        import subprocess

        subprocess.run(["bash", "-n", str(LAMBDA_DIR / "deploy.sh")], check=True)

    def test_refuses_a_dirty_tree_before_touching_aws(self, script: str) -> None:
        assert script.index("Refusing to deploy: the working tree") < script.index("aws sts")

    def test_migrates_the_pushed_image_before_the_functions_move_to_it(self, script: str) -> None:
        push = script.index('docker push "$IMAGE"')
        migrate = script.index('"$IMAGE" migrate')
        deploy = script.index("sam deploy \\")
        assert push < migrate < deploy

    def test_migrates_through_the_direct_endpoint(self, script: str) -> None:
        assert "DATABASE_URL=${DATABASE_URL_DIRECT}" in script

    def test_no_secret_reaches_a_command_line(self, script: str) -> None:
        """Secrets go through 0600 files; argv is readable by every local process."""
        for line in script.splitlines():
            stripped = line.strip()
            if stripped.startswith(("docker run", "sam deploy", "aws cloudformation deploy")):
                for name in ("SESSION_SECRET", "ORIGIN_VERIFY_SECRET", "DATABASE_URL_"):
                    assert name not in stripped, stripped


def test_deploy_script_omits_empty_parameter_overrides() -> None:
    """SAM refuses `Key=` with no value, so unset optionals must be left out."""
    script = (LAMBDA_DIR / "deploy.sh").read_text()
    loop = script[script.index('"ImageUri=${IMAGE}"') :]
    assert '[ -n "${pair#*=}" ] || continue' in loop.split("done", 1)[0]


def test_deploy_script_strips_spaces_from_allowed_senders() -> None:
    """SAM splits override values on spaces; `a@x, b@y` must arrive as one value."""
    script = (LAMBDA_DIR / "deploy.sh").read_text()
    assert 'INBOX_ALLOWED_SENDERS="${INBOX_ALLOWED_SENDERS// /}"' in script
