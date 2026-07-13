"""Unit tests for the Terraform ecosystem plugin."""

import pytest

from backend.data_sources.terraform_plugin import TerraformPlugin


class TestParseTerraformLock:
    """Tests for TerraformPlugin.parse_terraform_lock()."""

    def test_single_provider(self):
        content = """\
# This is a lock file
provider "registry.terraform.io/hashicorp/aws" {
  version     = "5.0.0"
  constraints = "~> 5.0.0"
  hashes = [
    "h1:abc123",
  ]
}
"""
        result = TerraformPlugin.parse_terraform_lock(content)
        assert len(result) == 1
        assert result[0]["name"] == "registry.terraform.io/hashicorp/aws"
        assert result[0]["version"] == "5.0.0"
        assert result[0]["_ecosystem"] == "terraform"

    def test_multiple_providers(self):
        content = """\
provider "registry.terraform.io/hashicorp/aws" {
  version = "5.0.0"
}
provider "registry.terraform.io/hashicorp/azurerm" {
  version = "3.0.0"
}
"""
        result = TerraformPlugin.parse_terraform_lock(content)
        assert len(result) == 2
        assert result[0]["name"] == "registry.terraform.io/hashicorp/aws"
        assert result[0]["version"] == "5.0.0"
        assert result[1]["name"] == "registry.terraform.io/hashicorp/azurerm"
        assert result[1]["version"] == "3.0.0"

    def test_empty_content(self):
        result = TerraformPlugin.parse_terraform_lock("")
        assert result == []

    def test_version_constraint(self):
        content = """\
provider "registry.terraform.io/hashicorp/random" {
  version     = "3.5.0"
  constraints = "~> 3.0"
}
"""
        result = TerraformPlugin.parse_terraform_lock(content)
        assert len(result) == 1
        assert result[0]["name"] == "registry.terraform.io/hashicorp/random"
        assert result[0]["version"] == "3.5.0"

    def test_with_hashes(self):
        content = """\
provider "registry.terraform.io/hashicorp/local" {
  version = "2.4.0"
  hashes = [
    "h1:abc123def456",
    "h1:789ghi012jkl",
  ]
}
"""
        result = TerraformPlugin.parse_terraform_lock(content)
        assert len(result) == 1
        assert result[0]["name"] == "registry.terraform.io/hashicorp/local"
        assert result[0]["version"] == "2.4.0"

    def test_comments_only(self):
        content = """\
# just a comment
# another comment
"""
        result = TerraformPlugin.parse_terraform_lock(content)
        assert result == []


class TestTerraformPlugin:
    """Tests for TerraformPlugin class metadata and stubs."""

    def test_ecosystem_name(self):
        assert TerraformPlugin.ecosystem == "terraform"

    def test_manifest_patterns(self):
        assert len(TerraformPlugin.manifests) == 1
        assert TerraformPlugin.manifests[0].glob == ".terraform.lock.hcl"
        assert TerraformPlugin.manifests[0].parser == "parse_terraform_lock"

    def test_no_lock_files(self):
        assert len(TerraformPlugin.lock_files) == 0

    @pytest.mark.asyncio
    async def test_get_package_info_stub(self):
        plugin = TerraformPlugin(cache_ttl=0)
        result = await plugin.get_package_info("hashicorp/aws")
        assert result is not None
        assert result["name"] == "hashicorp/aws"
        assert result["ecosystem"] == "terraform"
        assert result["version"] == "latest"
