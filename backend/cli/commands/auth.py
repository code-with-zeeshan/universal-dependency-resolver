"""Manage DB-backed API keys for the UDR API server."""

import secrets

from rich import box
from rich.table import Table

from ..shared import console


def _get_db():
    from backend.database.models import db_session

    return db_session()


def _generate_key() -> str:
    return f"udr_{secrets.token_urlsafe(32)}"


def cmd_auth(args):
    """Manage API keys — create, revoke, list."""
    from backend.database.models import APIKey

    if args.auth_action == "create":
        name = args.name or "cli-generated"
        role = args.role or "read-only"
        key_str = _generate_key()

        scopes = {"admin": ["admin"], "read-write": ["read", "write"], "read-only": ["read"]}.get(
            role, ["read"]
        )

        with _get_db() as session:
            db_key = APIKey(
                key=key_str,
                name=name,
                description=args.description or "",
                scopes=scopes,
                is_active=True,
            )
            session.add(db_key)
            session.commit()
            key_id = db_key.id

        console.print(f"[green]API key created:[/green] {key_str}")
        console.print(f"  ID:   {key_id}")
        console.print(f"  Name: {name}")
        console.print(f"  Role: {role}")
        console.print("[yellow]Store this key securely — it will not be shown again.[/yellow]")

    elif args.auth_action == "revoke":
        key_id = args.key_id

        with _get_db() as session:
            db_key = session.query(APIKey).filter(APIKey.id == key_id).first()
            if not db_key:
                console.print(f"[red]API key with ID {key_id} not found[/red]")
                return 1
            db_key.is_active = False
            session.commit()

        console.print(f"[green]API key {key_id} revoked.[/green]")

    elif args.auth_action == "list":
        table = Table(title="API Keys", box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Role", style="green")
        table.add_column("Active", style="yellow")
        table.add_column("Last Used")
        table.add_column("Usage Count")

        with _get_db() as session:
            keys = session.query(APIKey).order_by(APIKey.created_at.desc()).all()
            for k in keys:
                scopes = k.scopes or []
                role = (
                    "admin"
                    if "admin" in scopes
                    else "read-write"
                    if "write" in scopes
                    else "read-only"
                )
                last_used = k.last_used_at.isoformat()[:19] if k.last_used_at else "never"
                active = "[green]yes[/green]" if k.is_active else "[red]no[/red]"
                table.add_row(str(k.id), k.name, role, active, last_used, str(k.usage_count or 0))

        console.print(table)

    else:
        console.print(f"[red]Unknown auth action: {args.auth_action}[/red]")
        return 1

    return 0
