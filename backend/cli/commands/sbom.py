"""Generate SPDX 2.3 or CycloneDX 1.5 SBOM from udr.lock."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.utils import make_purl

from ..shared import _read_lock_file, _resolve_lock_path, console


def _build_spdx(lock_data: dict, lock_path: Path) -> dict[str, Any]:
    packages_raw = lock_data.get("packages", {})
    spdx_packages = []
    spdx_relationships = []

    for pkg_name, pkg_info in packages_raw.items():
        ver = pkg_info.get("resolved_version", "")
        lic = pkg_info.get("license") or "NOASSERTION"
        integrity = pkg_info.get("integrity")

        pkg_entry = {
            "SPDXID": f"SPDXRef-{pkg_name}",
            "name": pkg_name,
            "versionInfo": ver,
            "supplier": "NOASSERTION",
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": lic,
            "licenseDeclared": lic,
            "copyrightText": "NOASSERTION",
        }
        if integrity and isinstance(integrity, dict):
            algo = integrity.get("algorithm", "SHA256")
            val = integrity.get("value", "")
            if val:
                pkg_entry["checksums"] = [{"algorithm": algo, "value": val}]

        spdx_packages.append(pkg_entry)

        for dep_name in pkg_info.get("depends_on", {}):
            spdx_relationships.append(
                {
                    "spdxElementId": f"SPDXRef-{pkg_name}",
                    "relatedSpdxElement": f"SPDXRef-{dep_name}",
                    "relationshipType": "DEPENDS_ON",
                }
            )

    lock_filename = lock_path.name
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"udr-sbom-{lock_filename}",
        "creationInfo": {
            "created": datetime.now().isoformat(),
            "creators": ["Tool: universal-dependency-resolver"],
        },
        "packages": spdx_packages,
        "relationships": spdx_relationships,
    }


def _build_cyclonedx(lock_data: dict) -> dict[str, Any]:
    packages_raw = lock_data.get("packages", {})
    components = []
    dependencies = []
    purl_cache = {}

    for pkg_name, pkg_info in packages_raw.items():
        eco = pkg_info.get("ecosystem", "pypi")
        ver = pkg_info.get("resolved_version", "")
        lic = pkg_info.get("license")
        purl_str = make_purl(pkg_name, ver, eco)
        purl_cache[pkg_name] = purl_str

        comp = {
            "type": "library",
            "name": pkg_name,
            "version": ver,
            "purl": purl_str,
        }
        if lic:
            comp["licenses"] = [{"license": {"id": lic}}]
        components.append(comp)

    for pkg_name, pkg_info in packages_raw.items():
        dep_ref = purl_cache.get(pkg_name, "")
        dep_on = [purl_cache.get(d) for d in pkg_info.get("depends_on", {}) if purl_cache.get(d)]
        if dep_on:
            dependencies.append({"ref": dep_ref, "dependsOn": dep_on})

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "tools": [{"name": "universal-dependency-resolver"}],
        },
        "components": components,
        "dependencies": dependencies,
    }


def cmd_sbom(args: argparse.Namespace) -> None:
    """Generate SBOM from lock file."""
    directory = Path(args.directory).resolve()
    lock_path = _resolve_lock_path(
        directory,
        workspace=args.workspace,
        lock_file=args.lock_file,
    )
    if not lock_path.is_file():
        console.print(f"[red]No lock file found at {lock_path}[/red]")
        console.print("Run [bold]udr lock[/bold] first to generate one.")
        sys.exit(1)

    lock_data = _read_lock_file(lock_path)
    fmt = args.format
    doc = _build_cyclonedx(lock_data) if fmt == "cyclonedx" else _build_spdx(lock_data, lock_path)

    output = args.output
    json_str = json.dumps(doc, indent=2)

    if output:
        Path(output).write_text(json_str)
        console.print(f"[green]SBOM written:[/green] {output}")
    else:
        print(json_str)

    sys.exit(0)
