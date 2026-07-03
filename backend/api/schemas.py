"""Module docstring."""
from typing import List, Dict, Optional
from pydantic import BaseModel, field_validator
import re


class PackageRequest(BaseModel):
    """Package Request functionality."""

    name: str
    ecosystem: Optional[str] = None
    version: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate name."""
        if not re.match(r"^[a-zA-Z0-9\-_\.]+$", v):
            raise ValueError("Invalid package name")
        return v


class SystemInfo(BaseModel):
    """System Info functionality."""

    gpu: Optional[Dict] = None
    os: Optional[Dict] = None
    cpu: Optional[Dict] = None
    runtime_versions: Optional[Dict] = None


class ResolveRequest(BaseModel):
    """Resolve Request functionality."""

    packages: List[PackageRequest]
    system_info: Optional[SystemInfo] = None
    auto_detect_system: bool = True
    prefer_compatibility: bool = True


class ExportRequest(BaseModel):
    """Export Request functionality."""

    resolved_packages: Dict
    format: str
    system_info: Optional[Dict] = None
    options: Optional[Dict] = None
