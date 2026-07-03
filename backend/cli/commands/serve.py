"""Module docstring."""

import sys

from rich.panel import Panel

from ..shared import console


def cmd_serve(args):
    """Cmd serve."""
    try:
        import uvicorn

        from backend.api.main import app

        console.print("[bold green]Starting UDR API server...[/bold green]")
        console.print(f"  Mode: [cyan]{args.mode}[/cyan]")
        console.print(f"  Host: [yellow]{args.host}[/yellow]  Port: [yellow]{args.port}[/yellow]")
        if args.log_level:
            console.print(f"  Log level: [dim]{args.log_level}[/dim]")
        if args.workers:
            console.print(f"  Workers: [dim]{args.workers}[/dim]")
        if args.ssl_keyfile and args.ssl_certfile:
            console.print("  SSL: [dim]enabled[/dim]")

        kwargs = {
            "host": args.host,
            "port": args.port,
            "reload": args.reload,
            "log_level": args.log_level,
        }
        if args.workers:
            kwargs["workers"] = args.workers
        if args.ssl_keyfile and args.ssl_certfile:
            kwargs["ssl_keyfile"] = args.ssl_keyfile
            kwargs["ssl_certfile"] = args.ssl_certfile

        uvicorn.run(app, **kwargs)
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Server Error"))
        sys.exit(1)
