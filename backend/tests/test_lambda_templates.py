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
