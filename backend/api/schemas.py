"""Module docstring."""

import re

from pydantic import BaseModel, field_validator


class PackageRequest(BaseModel):
    """Package Request functionality."""

    name: str
    ecosystem: str | None = None
    version: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name."""
        if not re.match(r"^[a-zA-Z0-9\-_\.]+$", v):
            raise ValueError("Invalid package name")
        return v


class SystemInfo(BaseModel):
    """System Info functionality."""

    gpu: dict | None = None
    os: dict | None = None
    cpu: dict | None = None
    runtime_versions: dict | None = None


class ResolveRequest(BaseModel):
    """Resolve Request functionality."""

    packages: list[PackageRequest]
    system_info: SystemInfo | None = None
    auto_detect_system: bool = True
    prefer_compatibility: bool = True


class ExportRequest(BaseModel):
    """Export Request functionality."""

    resolved_packages: dict
    format: str
    system_info: dict | None = None
    options: dict | None = None
