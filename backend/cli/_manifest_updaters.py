"""Manifest file updaters — modify manifest files with pinned versions."""

import json
import re


def _update_package_json(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update package.json content with pinned version.

    Replaces version in dependencies, devDependencies, and peerDependencies.
    Returns updated content or None if the package was not found.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    updated = False
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        if section in data and pkg_name in data[section]:
            data[section][pkg_name] = resolved_ver
            updated = True
    if not updated:
        return None
    return json.dumps(data, indent=2) + "\n"


def _update_pubspec_yaml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update pubspec.yaml content with pinned version.

    Replaces version in dependencies and dev_dependencies sections.
    Returns updated content or None if the package was not found.
    """
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_deps = False
    in_dev_deps = False
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped == "dependencies:":
            in_deps = True
            in_dev_deps = False
        elif stripped == "dev_dependencies:":
            in_dev_deps = True
            in_deps = False
        elif stripped == "dependency_overrides:" or (
            stripped and not stripped.startswith("#") and not indent
        ):
            in_deps = False
            in_dev_deps = False
        if (in_deps or in_dev_deps) and stripped.startswith(pkg_name + ":"):
            new_lines.append(f"{indent}{pkg_name}: {resolved_ver}")
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_go_mod(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_require_block = False
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith("require (") and stripped.endswith(")"):
            parts = stripped[len("require (") : -len(")")].strip().split()
            if len(parts) >= 2 and parts[0] == pkg_name:
                new_lines.append(f"{indent}require ({pkg_name} {resolved_ver})")
                updated = True
                continue
            new_lines.append(line)
        elif stripped == "require (":
            in_require_block = True
            new_lines.append(line)
        elif in_require_block and stripped == ")":
            in_require_block = False
            new_lines.append(line)
        elif in_require_block:
            parts = stripped.split()
            if len(parts) >= 2 and parts[0] == pkg_name:
                trail = " ".join(parts[2:]) if len(parts) > 2 else ""
                comment = " " + trail if trail else ""
                new_lines.append(f"{indent}{pkg_name} {resolved_ver}{comment}")
                updated = True
            else:
                new_lines.append(line)
        elif stripped.startswith("require " + pkg_name + " "):
            trail = stripped[len("require " + pkg_name + " ") :]
            comment = ""
            if "//" in trail:
                comment = " //" + trail.split("//", 1)[1]
            new_lines.append(f"{indent}require {pkg_name} {resolved_ver}{comment}")
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_cargo_toml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_deps = False
    in_sub_dep = False
    sub_dep_name = ""
    dep_sections = {
        "[dependencies]",
        "[build-dependencies]",
        "[dev-dependencies]",
        "[workspace.dependencies]",
    }
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        # Check for [dependencies.pkg_name] sub-table format
        sub_match = re.match(
            r"^\[(dependencies|build-dependencies|dev-dependencies|workspace\.dependencies)\.(.+)\]$",
            stripped,
        )
        if stripped in dep_sections:
            in_deps = True
            in_sub_dep = False
            sub_dep_name = ""
            new_lines.append(line)
        elif sub_match:
            in_deps = False
            in_sub_dep = True
            sub_dep_name = sub_match.group(2)
            new_lines.append(line)
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_deps = False
            in_sub_dep = False
            sub_dep_name = ""
            new_lines.append(line)
        elif in_sub_dep and sub_dep_name == pkg_name and stripped.startswith("version"):
            eq_pos = stripped.find("=")
            if eq_pos > 0:
                comment = ""
                after = stripped[eq_pos + 1 :].strip()
                if "#" in after:
                    comment = " #" + after.split("#", 1)[1]
                new_lines.append(f'{indent}version = "{resolved_ver}"{comment}')
                updated = True
                continue
            new_lines.append(line)
        elif in_deps and stripped.startswith(pkg_name):
            eq_pos = stripped.find("=")
            if eq_pos > 0:
                before = stripped[:eq_pos].strip()
                if before == pkg_name:
                    after = stripped[eq_pos + 1 :].strip()
                    after_no_comment = after.split("#")[0].strip() if "#" in after else after
                    has_braces = after_no_comment.startswith("{")
                    comment = ""
                    if "#" in after:
                        comment = " #" + after.split("#", 1)[1]
                    if has_braces:
                        new_lines.append(
                            f'{indent}{pkg_name} = {{ version = "{resolved_ver}" }}{comment}'
                        )
                    else:
                        outer_q = ""
                        for q in ['"', "'"]:
                            if after_no_comment.startswith(q):
                                outer_q = q
                                break
                        if outer_q:
                            new_lines.append(
                                f"{indent}{pkg_name} = {outer_q}{resolved_ver}{outer_q}{comment}"
                            )
                        else:
                            new_lines.append(f'{indent}{pkg_name} = "{resolved_ver}"{comment}')
                    updated = True
                    continue
            new_lines.append(line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_gemfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith("gem "):
            for q in ['"', "'"]:
                gem_prefix = f"gem {q}{pkg_name}{q}"
                if stripped.startswith(gem_prefix):
                    rest = stripped[len(gem_prefix) :].strip()
                    if rest.startswith(","):
                        rest = rest[1:].strip()
                    if rest.startswith(","):
                        rest = rest[1:].strip()
                    comment = ""
                    if "#" in rest:
                        comment = " #" + rest.split("#", 1)[1]
                    new_lines.append(f'{indent}gem {q}{pkg_name}{q}, "{resolved_ver}"{comment}')
                    updated = True
                    break
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_composer_json(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    updated = False
    for section in ("require", "require-dev"):
        if section in data and pkg_name in data[section]:
            data[section][pkg_name] = resolved_ver
            updated = True
    if not updated:
        return None
    return json.dumps(data, indent=2) + "\n"


def _update_pyproject_toml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    try:
        import tomllib

        data = tomllib.loads(content)
    except Exception:
        return None

    # Check if pkg_name exists in either [tool.poetry.dependencies] or [project] dependencies
    found_poetry = False
    found_project = False

    if "tool" in data and "poetry" in data["tool"]:
        for section in ("dependencies", "dev-dependencies"):
            if section in data["tool"]["poetry"] and pkg_name in data["tool"]["poetry"][section]:
                found_poetry = True
                break

    if "project" in data and "dependencies" in data["project"]:
        for dep_str in data["project"]["dependencies"]:
            try:
                from packaging.requirements import Requirement

                req = Requirement(dep_str)
                if req.name == pkg_name:
                    found_project = True
                    break
            except Exception:
                if dep_str.startswith(pkg_name) and any(c in dep_str for c in "=<>~!"):
                    found_project = True
                    break

    if not found_poetry and not found_project:
        return None

    # Now do string-level replacement
    lines = content.split("\n")
    new_lines: list[str] = []
    in_poetry_deps = False
    in_poetry_dev = False
    in_project_deps = False
    updated = False

    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        if stripped == "[tool.poetry.dependencies]":
            in_poetry_deps = True
            in_poetry_dev = False
            in_project_deps = False
            new_lines.append(line)
        elif stripped == "[tool.poetry.dev-dependencies]":
            in_poetry_deps = False
            in_poetry_dev = True
            in_project_deps = False
            new_lines.append(line)
        elif stripped.startswith("[tool.poetry") or stripped in ("[project]",):
            in_poetry_deps = False
            in_poetry_dev = False
            in_project_deps = False
            new_lines.append(line)
        elif stripped == "dependencies = [":
            in_project_deps = True
            in_poetry_deps = False
            in_poetry_dev = False
            new_lines.append(line)
        elif stripped.startswith("dependencies = "):
            new_lines.append(line)
        elif stripped == "]":
            in_project_deps = False
            new_lines.append(line)
        elif in_poetry_deps or in_poetry_dev:
            eq_pos = stripped.find("=")
            if eq_pos > 0 and stripped[:eq_pos].strip() == pkg_name:
                comment = ""
                after = stripped[eq_pos + 1 :].strip()
                if "#" in after:
                    comment = " #" + after.split("#", 1)[1]
                for q in ['"', "'"]:
                    if after.startswith(q):
                        outer_q = q
                        break
                else:
                    outer_q = '"'
                new_lines.append(f"{indent}{pkg_name} = {outer_q}{resolved_ver}{outer_q}{comment}")
                updated = True
            else:
                new_lines.append(line)
        elif in_project_deps:
            str_stripped = stripped.strip(",").strip()
            if str_stripped.startswith(('"', "'")):
                raw = str_stripped.strip(",").strip("\"'")
                try:
                    from packaging.requirements import Requirement

                    req = Requirement(raw)
                    match_name = req.name == pkg_name
                except Exception:
                    match_name = raw.startswith(pkg_name) and any(c in raw for c in "=<>~!")
                if match_name:
                    comment = ""
                    if "#" in stripped:
                        comment = " #" + stripped.split("#", 1)[1]
                    trailing_comma = "," if stripped.rstrip().endswith(",") else ""
                    new_lines.append(
                        f'{indent}"{pkg_name}=={resolved_ver}"{trailing_comma}{comment}'
                    )
                    updated = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return "\n".join(new_lines) + "\n" if updated else None


def _update_build_gradle(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith(("//", "*", "/*")):
            new_lines.append(line)
            continue
        for prefix in (
            "implementation",
            "api",
            "compile",
            "runtimeOnly",
            "compileOnly",
            "testImplementation",
            "androidTestImplementation",
            "kapt",
            "annotationProcessor",
        ):
            pattern = re.escape(prefix) + r"\s+['\"]" + re.escape(pkg_name) + r"['\"]"
            if re.match(pattern, stripped):
                new_lines.append(f"{indent}{prefix} '{pkg_name}:{resolved_ver}'")
                updated = True
                break
            pattern_full = re.escape(prefix) + r"\s+['\"]" + re.escape(pkg_name) + r":\S+['\"]"
            if re.match(pattern_full, stripped):
                new_lines.append(f"{indent}{prefix} '{pkg_name}:{resolved_ver}'")
                updated = True
                break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_mix_exs(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        m = re.match(r"\{:\s*" + re.escape(pkg_name) + r'\s*,\s*"[^"]*"\s*\}', stripped)
        if m:
            new_lines.append(f'{indent}{{:{pkg_name}, "{resolved_ver}"}}')
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_package_swift(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        m = re.search(
            r'\.package\(url:\s*"[^"]*'
            + re.escape(pkg_name)
            + r'[^"]*"\s*,\s*from\s*:\s*"([^"]+)"\s*\)',
            stripped,
        )
        if m:
            before = m.group(1)
            new_line = stripped.replace(f'from: "{before}"', f'from: "{resolved_ver}"')
            new_lines.append(f"{indent}{new_line}")
            updated = True
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_podfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        for q in ['"', "'"]:
            pattern = f"pod {q}{pkg_name}{q}"
            if stripped.startswith(pattern):
                rest = stripped[len(pattern) :].strip().strip(",").strip()
                comment = ""
                if "#" in rest:
                    comment = " #" + rest.split("#", 1)[1]
                new_lines.append(f'{indent}pod {q}{pkg_name}{q}, "{resolved_ver}"{comment}')
                updated = True
                break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_gemspec_dependency(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        for prefix in (
            "s.add_dependency",
            "s.add_runtime_dependency",
            "s.add_development_dependency",
            "add_dependency",
            "add_runtime_dependency",
            "add_development_dependency",
        ):
            for q in ['"', "'"]:
                pattern = (
                    re.escape(prefix)
                    + r"\s*\(\s*"
                    + re.escape(q)
                    + re.escape(pkg_name)
                    + re.escape(q)
                )
                if re.match(pattern, stripped):
                    before_rest = stripped[
                        stripped.find(q + pkg_name + q) + len(q + pkg_name + q) :
                    ].strip()
                    comment = ""
                    if "#" in before_rest:
                        comment = " #" + before_rest.split("#", 1)[1]
                    new_lines.append(
                        f'{indent}{prefix} {q}{pkg_name}{q}, "{resolved_ver}"{comment}'
                    )
                    updated = True
                    break
                pattern2 = (
                    re.escape(prefix) + r"\s+" + re.escape(q) + re.escape(pkg_name) + re.escape(q)
                )
                if re.match(pattern2, stripped):
                    before_rest = stripped[
                        stripped.find(q + pkg_name + q) + len(q + pkg_name + q) :
                    ].strip()
                    comment = ""
                    if "#" in before_rest:
                        comment = " #" + before_rest.split("#", 1)[1]
                    new_lines.append(
                        f'{indent}{prefix} {q}{pkg_name}{q}, "{resolved_ver}"{comment}'
                    )
                    updated = True
                    break
            else:
                continue
            break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_brewfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update Brewfile content with pinned version.

    Handles both gem and cask entries.
    """
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        for q in ['"', "'"]:
            for kind in ("brew", "cask", "gem"):
                prefix = f"{kind} {q}{pkg_name}{q}"
                if stripped.startswith(prefix):
                    rest = stripped[len(prefix) :].strip().strip(",").strip()
                    comment = ""
                    if "#" in rest:
                        comment = " #" + rest.split("#", 1)[1]
                    new_lines.append(f'{indent}{kind} {q}{pkg_name}{q}, "{resolved_ver}"{comment}')
                    updated = True
                    break
            else:
                continue
            break
        else:
            new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_pipfile(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update Pipfile content with pinned version.

    Handles both simple (pkg = ">=1.0") and extended (pkg = {version = ">=1.0"}) formats.
    """
    updated = False
    in_packages = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped in ("[packages]", "[dev-packages]"):
            in_packages = True
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_packages = False
        if in_packages and "=" in stripped:
            key = stripped.split("=", 1)[0].strip().strip('"').strip("'")
            if key == pkg_name:
                value_part = stripped.split("=", 1)[1].strip()
                if value_part.startswith("{"):
                    new_lines.append(f'{indent}{pkg_name} = "=={resolved_ver}"')
                else:
                    new_lines.append(f'{indent}{pkg_name} = "=={resolved_ver}"')
                updated = True
                continue
        new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_packages_config(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update packages.config content with pinned version."""
    try:
        import xml.etree.ElementTree as ET
    except Exception:
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    updated = False
    for pkg_elem in root.findall("package"):
        pid = pkg_elem.get("id", "")
        if pid == pkg_name:
            pkg_elem.set("version", resolved_ver)
            updated = True
    if not updated:
        return None
    result = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return result + "\n"


def _update_environment_yml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update environment.yml content with pinned version.

    Handles both conda and pip dependency formats with any operator (=, >=, <=, !=, ~=, ==).
    """
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    in_deps = False
    pip_indent: str | None = None
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if stripped.startswith("dependencies:"):
            in_deps = True
            pip_indent = None
        elif in_deps and stripped == "":
            in_deps = False
            pip_indent = None
        if in_deps and stripped.startswith("- "):
            if stripped == "- pip:":
                pip_indent = indent
                new_lines.append(line)
                continue
            is_pip = pip_indent is not None and len(indent) > len(pip_indent)
            dep = stripped[2:].strip()
            found_op = None
            for op in ["==", ">=", "<=", "!=", "~=", "=", ">", "<"]:
                if op in dep:
                    name = dep.split(op, 1)[0].strip()
                    if name == pkg_name:
                        found_op = op
                        break
            if (found_op is None and dep == pkg_name) or found_op is not None:
                sep = "==" if is_pip else "="
                new_lines.append(f"{indent}- {pkg_name}{sep}{resolved_ver}")
                updated = True
                continue
        new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_cabal(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update .cabal file content with pinned version.

    Handles build-depends entries across continuation lines.
    """
    updated = False
    in_build_depends = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        if stripped.startswith("build-depends:"):
            in_build_depends = True
        elif (
            in_build_depends
            and not stripped.startswith(",")
            and not stripped.startswith("build-depends:")
        ):
            in_build_depends = False

        if in_build_depends:
            entry = stripped
            if entry.startswith("build-depends:"):
                entry = entry[len("build-depends:") :].strip()
            elif entry.startswith(","):
                entry = entry[1:].strip()
            parts = entry.split()
            if parts and parts[0] == pkg_name:
                comment = ""
                if "--" in entry:
                    comment = "  --" + entry.split("--", 1)[1]
                if entry.startswith("build-depends:"):
                    new_lines.append(
                        f"{indent}build-depends:    {pkg_name} =={resolved_ver},{comment}"
                    )
                else:
                    new_lines.append(f"{indent}, {pkg_name} =={resolved_ver}{comment}")
                updated = True
                continue

        new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_simple(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update apt-packages.txt / apk-packages.txt content with pinned version."""
    updated = False
    lines = content.split("\n")
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        comment = ""
        if "#" in stripped and not stripped.startswith("#"):
            comment = " #" + stripped.split("#", 1)[1]
            stripped = stripped.split("#", 1)[0].strip()
        matched = False
        for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
            if op in stripped:
                n, _ = stripped.split(op, 1)
                if n.strip() == pkg_name:
                    new_lines.append(f"{indent}{pkg_name}=={resolved_ver}{comment}")
                    updated = True
                    matched = True
                    break
                break
        if not matched:
            if stripped == pkg_name:
                new_lines.append(f"{indent}{pkg_name}=={resolved_ver}{comment}")
                updated = True
            else:
                new_lines.append(line)
    return "\n".join(new_lines) + "\n" if updated else None


def _update_pom_xml(content: str, pkg_name: str, resolved_ver: str) -> str | None:
    """Update Maven pom.xml with pinned version using namespace-aware XML parsing."""
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        return None
    try:
        root = ET.fromstring(content)
    except Exception:
        return None
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    updated = False
    for dep in root.findall(".//m:dependencies/m:dependency", ns):
        group = dep.find("m:groupId", ns)
        artifact = dep.find("m:artifactId", ns)
        version = dep.find("m:version", ns)
        if group is not None and artifact is not None:
            name = f"{group.text}:{artifact.text}"
            if name == pkg_name and version is not None:
                version.text = resolved_ver
                updated = True
    if not updated:
        return None
    ET.register_namespace("", ns["m"])
    result = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return result + "\n"


def _get_manifest_updater(filename: str):
    _updaters = {
        "package.json": _update_package_json,
        "pubspec.yaml": _update_pubspec_yaml,
        "go.mod": _update_go_mod,
        "Cargo.toml": _update_cargo_toml,
        "Gemfile": _update_gemfile,
        "composer.json": _update_composer_json,
        "pyproject.toml": _update_pyproject_toml,
        "build.gradle": _update_build_gradle,
        "build.gradle.kts": _update_build_gradle,
        "Package.swift": _update_package_swift,
        "mix.exs": _update_mix_exs,
        "Podfile": _update_podfile,
        "Brewfile": _update_brewfile,
        "Pipfile": _update_pipfile,
        "packages.config": _update_packages_config,
        "environment.yml": _update_environment_yml,
        "apt-packages.txt": _update_simple,
        "apk-packages.txt": _update_simple,
        "pom.xml": _update_pom_xml,
    }
    if filename in _updaters:
        return _updaters[filename]
    if filename.endswith(".gemspec"):
        return _update_gemspec_dependency
    if filename.endswith(".cabal"):
        return _update_cabal
    # Check plugin registry for ecosystem-specific updaters
    try:
        from backend.core.plugin import get_all_plugins

        for eco, cls in get_all_plugins().items():
            for mf in cls.manifests:
                if mf.glob == filename:
                    update_method = getattr(cls, f"update_{mf.parser}", None)
                    if update_method is not None:
                        return update_method
    except ImportError:
        pass
    return None
