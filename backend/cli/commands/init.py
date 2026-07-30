"""Initialize a new project with UDR configuration."""

import argparse
import json
import sys
from pathlib import Path

from ..shared import console

INIT_TEMPLATES: dict[str, dict[str, str]] = {
    "python-requirements": {
        "requirements.txt": "flask>=3.0\nrequests>=2.31\n",
    },
    "python-pyproject": {
        "pyproject.toml": '[project]\nname = "my-project"\nversion = "0.1.0"\ndependencies = [\n    "flask>=3.0",\n    "requests>=2.31",\n]\n',
    },
    "node": {
        "package.json": '{\n  "name": "my-project",\n  "version": "1.0.0",\n  "dependencies": {\n    "express": "^4.18.0"\n  }\n}\n',
    },
    "go": {
        "go.mod": "module my-project\n\ngo 1.21\n",
    },
    "rust": {
        "Cargo.toml": '[package]\nname = "my-project"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n',
    },
}


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new project."""
    directory = Path(args.directory).resolve()
    if not directory.exists():
        console.print(f"[yellow]Creating directory:[/yellow] {directory}")
        directory.mkdir(parents=True, exist_ok=True)

    template_name = args.template
    template = INIT_TEMPLATES.get(template_name)
    if not template:
        if template_name != "auto":
            console.print(f"[red]Unknown template:[/red] {template_name}")
            console.print(f"Available: {', '.join(INIT_TEMPLATES.keys())}")
            sys.exit(1)
        template = None

    files_written = 0
    if template:
        for filename, content in template.items():
            filepath = directory / filename
            if filepath.exists() and not args.force:
                console.print(
                    f"[yellow]Skipping {filename} (already exists, use --force to overwrite)[/yellow]"
                )
                continue
            filepath.write_text(content)
            console.print(f"[green]Created[/green] {filepath}")
            files_written += 1

    if args.with_config:
        config_path = directory / "udr.json"
        if config_path.exists() and not args.force:
            console.print(
                "[yellow]Skipping udr.json (already exists, use --force to overwrite)[/yellow]"
            )
        else:
            config: dict[str, object] = {
                "version": "1.0",
                "project": {"name": args.name or directory.name},
                "settings": {},
            }
            config_path.write_text(json.dumps(config, indent=2) + "\n")
            console.print(f"[green]Created[/green] {config_path}")
            files_written += 1

    if args.gitignore:
        gitignore_path = directory / ".gitignore"
        if gitignore_path.exists() and not args.force:
            console.print("[yellow]Skipping .gitignore (use --force to overwrite)[/yellow]")
        else:
            gitignore_path.write_text("# UDR lock files\nudr.lock\nudr-*.lock\n")
            console.print(f"[green]Created[/green] {gitignore_path}")
            files_written += 1

    if files_written == 0:
        console.print("[yellow]No files written (all exist, use --force to overwrite)[/yellow]")
    elif args.lock:
        console.print("\n[bold]Running initial lock...[/bold]")
        from .lock import cmd_lock as lock_cmd

        lock_args = argparse.Namespace(
            command="lock",
            directory=str(directory),
            workspace=None,
            lock_file=None,
            dry_run=False,
            json=False,
            check=False,
            yes=False,
            non_interactive=True,
            dev=False,
            no_optional=False,
            sign=False,
            provenance=False,
            cuda=None,
            device=None,
            target=None,
            platform=None,
            pin=False,
        )
        try:
            lock_cmd(lock_args)
            console.print("[green]Initial lock completed[/green]")
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]Lock failed:[/red] {e}")


def add_init_parser(sub: argparse._SubParsersAction) -> None:
    """Add the init subparser."""
    init_p = sub.add_parser(
        "init",
        help="Initialize a new project with UDR configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  udr init -t python-requirements   # Python project
  udr init -t node --with-config --gitignore
  udr init -t go --lock
""",
    )
    init_p.add_argument(
        "--template",
        "-t",
        default="auto",
        choices=list(INIT_TEMPLATES.keys()),
        help="Project template (default: auto-detect from directory)",
    )
    init_p.add_argument(
        "--name",
        "-n",
        default=None,
        help="Project name (default: directory name)",
    )
    init_p.add_argument(
        "--directory",
        "-d",
        default=".",
        help="Project directory (default: current directory)",
    )
    init_p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing files",
    )
    init_p.add_argument(
        "--with-config",
        action="store_true",
        help="Create udr.json configuration file",
    )
    init_p.add_argument(
        "--gitignore",
        action="store_true",
        help="Create .gitignore with UDR entries",
    )
    init_p.add_argument(
        "--lock",
        action="store_true",
        help="Run initial lock after initialization",
    )
