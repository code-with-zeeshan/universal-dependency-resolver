import sys

from rich.panel import Panel

from ..shared import console, err_console


def cmd_serve(args):
    try:
        from backend.api.main import app
        import uvicorn

        console.print("[bold green]Starting UDR API server...[/bold green]")
        console.print(f"  Mode: [cyan]{args.mode}[/cyan]")
        console.print(
            f"  Host: [yellow]{args.host}[/yellow]  Port: [yellow]{args.port}[/yellow]"
        )
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(Panel(f"[red]{e}[/red]", title="Server Error"))
        sys.exit(1)
