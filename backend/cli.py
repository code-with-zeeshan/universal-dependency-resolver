"""
CLI entry point for Universal Dependency Resolver.

Usage:
    udr serve            Start the API server
    udr check            Check system compatibility
    udr resolve <pkg>    Resolve dependencies for a package
    udr info             Show system information
    udr lock             Auto-detect manifests and resolve all deps
"""

import argparse
import sys


def cmd_serve(args):
    from backend.api.main import app
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


def cmd_check(args):
    from backend.core import SystemScanner
    import asyncio

    async def _check():
        scanner = SystemScanner()
        info = await scanner.scan_all()
        ok = True
        print("System Compatibility Check")
        print("=" * 40)
        print(f"  OS:     {info['platform']['system']} {info['platform']['release']}")
        print(f"  CPU:    {info['cpu']['brand']} ({info['cpu']['count']} cores)")
        if info["gpu"]["available"]:
            gpu = info["gpu"]["devices"][0]
            print(f"  GPU:    {gpu['name']} ({gpu['memory_total']} MB)")
            print(f"  CUDA:   {info['gpu'].get('cuda', 'not found')}")
        else:
            print(f"  GPU:    None")
        py = info["runtime_versions"]["python"]
        print(f"  Python: {py['version']}")
        if args.verbose:
            print(f"  Python path: {py['location']}")
            print(f"  CPU arch:    {info['cpu']['arch']}")
            if info["gpu"].get("cuda"):
                print(f"  CUDA version: {info['gpu']['cuda']}")
        return ok

    sys.exit(0 if asyncio.run(_check()) else 1)


def cmd_resolve(args):
    from backend.core import DataAggregator, ConflictResolver
    import asyncio

    async def _resolve():
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        results = []
        for pkg in args.packages:
            ecosystem = args.ecosystem
            data = await aggregator.get_package_info(pkg, ecosystem=ecosystem)
            if data:
                resolved = resolver.resolve([data])
                results.append((pkg, resolved))
            else:
                print(f"Warning: {pkg} not found in {ecosystem}", file=sys.stderr)
        if args.format == "json":
            import json
            json.dump(
                [
                    {"package": pkg, "resolved": res.to_dict() if hasattr(res, "to_dict") else str(res)}
                    for pkg, res in results
                ],
                sys.stdout,
                indent=2,
            )
            print()
        else:
            for pkg, resolved in results:
                print(f"{pkg} -> {resolved}")
        return 0

    sys.exit(asyncio.run(_resolve()))


def cmd_info(args):
    from backend.core import SystemScanner
    import asyncio

    async def _info():
        scanner = SystemScanner()
        info = await scanner.scan_all()
        print(f"System Information for {info['platform']['system']} {info['platform']['release']}")
        print(f"  Architecture: {info['platform']['machine']}")
        print(f"  CPU: {info['cpu']['brand']} ({info['cpu']['count']} cores)")
        print(f"  Python: {info['runtime_versions']['python']['version']}")
        print(f"  Python path: {info['runtime_versions']['python']['location']}")
        if info["gpu"]["available"]:
            gpu = info["gpu"]["devices"][0]
            print(f"  GPU: {gpu['name']} ({gpu['memory_total']} MB)")
            cuda = info["gpu"].get("cuda")
            if cuda:
                print(f"  CUDA: {cuda}")
        from pathlib import Path
        import tomllib
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.is_file():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            deps = data.get("project", {}).get("dependencies", [])
            print(f"\nInstalled ({len(deps)} core packages)")
            for d in deps:
                print(f"  {d}")

    asyncio.run(_info())


def cmd_lock(args):
    import asyncio
    import json
    from pathlib import Path

    from backend.manifest_detector import ManifestDetector
    from backend.core import DataAggregator, ConflictResolver, SystemScanner
    from backend.core.export_generator import ExportGenerator

    async def _lock():
        directory = Path(args.directory).resolve()
        detector = ManifestDetector(str(directory))
        aggregator = DataAggregator()
        resolver = ConflictResolver()
        scanner = SystemScanner()
        exporter = ExportGenerator()

        # 1. Detect manifests
        manifests = detector.detect()
        if not manifests:
            print(f"No dependency manifests found in {directory}", file=sys.stderr)
            print("Checked for: requirements.txt, package.json, Cargo.toml, pyproject.toml,", file=sys.stderr)
            print("             Pipfile, environment.yml, Gemfile, go.mod, composer.json", file=sys.stderr)
            return 1

        print(f"Found {len(manifests)} manifest(s) in {directory}:")
        for m in manifests:
            print(f"  [{m['ecosystem']:>10}] {m['filename']}")
        print()

        # 2. Parse all manifests
        packages = detector.normalize(detector.parse_all(manifests))
        if not packages:
            print("No packages found in manifests", file=sys.stderr)
            return 1

        print(f"Found {len(packages)} package(s):")
        for pkg in packages:
            print(f"  [{pkg['ecosystem']:>10}] {pkg['name']} ({pkg['constraint']}) — from {pkg['source']}")
        print()

        # 3. Fetch metadata for each unique (name, ecosystem)
        seen = set()
        fetched = []
        for pkg in packages:
            key = (pkg["name"], pkg["ecosystem"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  Fetching {pkg['name']} from {pkg['ecosystem']}...")
            try:
                info = await aggregator.get_package_info(
                    pkg["name"],
                    ecosystem=pkg["ecosystem"],
                )
                if info and info.get("version"):
                    fetched.append(info)
                    print(f"    → {info['version']}")
                else:
                    print(f"    → not found")
            except Exception as e:
                print(f"    → error: {e}")

        if not fetched:
            print("No package data could be fetched", file=sys.stderr)
            return 1

        # 4. Scan system
        print("\nScanning system...")
        system_info = await scanner.scan_all()

        # 5. Resolve conflicts
        print("Resolving dependencies...")
        resolved = resolver.resolve(fetched)

        # 6. Build lock data
        lock_data = {
            "version": "1.0",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "system": {
                "os": f"{system_info['platform']['system']} {system_info['platform']['release']}",
                "python": system_info["runtime_versions"]["python"]["version"],
                "cpu": system_info["cpu"]["brand"],
                "gpu": system_info["gpu"]["devices"][0]["name"] if system_info["gpu"]["available"] else None,
            },
            "manifests": [m["filename"] for m in manifests],
            "packages": {
                p["name"]: {
                    "name": p["name"],
                    "ecosystem": p["ecosystem"],
                    "resolved_version": resolved.get(p["name"], {}).get("version") if isinstance(resolved, dict) else None,
                    "original_constraint": p["constraint"],
                    "source": p["source"],
                }
                for p in packages
            },
            "resolution": str(resolved),
        }

        # 7. Write lock file
        lock_path = directory / "udr-lock.json"
        lock_path.write_text(json.dumps(lock_data, indent=2))
        print(f"\nLock file written: {lock_path}")

        # 8. Export if requested
        if args.export:
            export_format = args.export
            print(f"Exporting as {export_format}...")
            try:
                export_content = exporter.generate(
                    {p["name"]: {"version": lock_data["packages"][p["name"]]["resolved_version"], "ecosystem": p["ecosystem"]} for p in packages},
                    format=export_format,
                    system_info=system_info,
                )
                export_path = directory / f"udr-output.{export_format.replace('.', '-')}"
                export_path.write_text(export_content)
                print(f"Exported: {export_path}")
            except Exception as e:
                print(f"Export failed: {e}")

        # 9. Prompt to update manifests in-place
        if not args.yes and not args.dry_run:
            answer = input("\nUpdate manifests in-place with pinned versions? [y/N] ").strip().lower()
            args.yes = answer in ("y", "yes")

        if args.dry_run:
            print("\n[dry-run] No files were modified.")
            return 0

        if args.yes:
            # Update each manifest with pinned versions
            for pkg in packages:
                manifest_path = directory / pkg["source"]
                if not manifest_path.is_file():
                    continue
                resolved_ver = lock_data["packages"][pkg["name"]]["resolved_version"]
                if not resolved_ver:
                    continue
                content = manifest_path.read_text(encoding="utf-8", errors="replace")
                constraint = pkg["constraint"]
                # Only pin if constraint is a range (not already pinned)
                if constraint != resolved_ver and not constraint.startswith("=="):
                    old = f"{pkg['name']}{constraint}" if constraint != "*" else pkg["name"]
                    # Try to be smart about replacement
                    patterns = [
                        f"{pkg['name']} {constraint}" if constraint != "*" else pkg["name"],
                        f"{pkg['name']}{constraint}" if constraint != "*" else pkg["name"],
                        f'{pkg["name"]}>={constraint}' if constraint != "*" else None,
                    ]
                    new_line = f"{pkg['name']}=={resolved_ver}"
                    # Simple line-based replacement for requirements.txt
                    new_content = []
                    replaced = False
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if not replaced and stripped.startswith(pkg["name"]):
                            for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
                                if op in stripped:
                                    name_part = stripped.split(op)[0].strip()
                                    if name_part == pkg["name"]:
                                        indent = line[:len(line) - len(line.lstrip())]
                                        new_content.append(f"{indent}{pkg['name']}=={resolved_ver}")
                                        replaced = True
                                        break
                            else:
                                # No operator found, add pin
                                indent = line[:len(line) - len(line.lstrip())]
                                new_content.append(f"{indent}{pkg['name']}=={resolved_ver}")
                                replaced = True
                        else:
                            new_content.append(line)
                    if replaced:
                        manifest_path.write_text("\n".join(new_content) + "\n")
                        print(f"  Updated {pkg['source']}: {pkg['name']} → {resolved_ver}")

        return 0

    sys.exit(asyncio.run(_lock()))


def main():
    parser = argparse.ArgumentParser(
        prog="udr",
        description="Universal Dependency Resolver — resolve dependencies across ecosystems",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind address")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_p.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    check_p = sub.add_parser("check", help="Check system compatibility")
    check_p.add_argument("-v", "--verbose", action="store_true", help="Show detailed info")

    resolve_p = sub.add_parser("resolve", help="Resolve dependencies for one or more packages")
    resolve_p.add_argument("packages", nargs="+", help="Package names to resolve")
    resolve_p.add_argument("--ecosystem", "-e", default="pypi", choices=["pypi", "npm", "cargo", "go"], help="Package ecosystem")
    resolve_p.add_argument("--format", "-f", default="text", choices=["text", "json"], help="Output format")

    info_p = sub.add_parser("info", help="Show system information")

    lock_p = sub.add_parser("lock", help="Auto-detect manifests, resolve all dependencies, write lock file")
    lock_p.add_argument("--directory", "-d", default=".", help="Project directory to scan (default: current)")
    lock_p.add_argument("--manifest", "-m", help="Only process a specific manifest file (auto-detect otherwise)")
    lock_p.add_argument("--export", help="Export to a specific format (e.g. requirements.txt, Dockerfile)")
    lock_p.add_argument("--yes", "-y", action="store_true", help="Update manifests in-place without prompting")
    lock_p.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")

    args = parser.parse_args()
    dispatch = {
        "serve": cmd_serve,
        "check": cmd_check,
        "resolve": cmd_resolve,
        "info": cmd_info,
        "lock": cmd_lock,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
