"""Manage DB-backed API keys and signing keys for UDR."""

import base64
import secrets
from pathlib import Path

from rich import box
from rich.table import Table

from ..shared import console

_SIGNING_DIR = Path.home() / ".config" / "udr"


def _get_db():
    from backend.database.models import db_session

    return db_session()


def _generate_key() -> str:
    return f"udr_{secrets.token_urlsafe(32)}"


def _load_signing_key() -> tuple | None:
    """Load existing Ed25519 signing key. Returns (private_key, public_key_bytes) or None."""
    key_path = _SIGNING_DIR / "signing.key"
    if not key_path.is_file():
        return None
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(private_key, ed25519.Ed25519PrivateKey):
        return None
    return (private_key, private_key.public_key().public_bytes_raw())


def _generate_signing_key() -> tuple:
    """Generate a new Ed25519 keypair. Returns (private_key, public_key_bytes)."""
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    return (private_key, private_key.public_key().public_bytes_raw())


def _save_signing_key(private_key) -> None:
    """Save private key to ~/.config/udr/signing.key."""
    from cryptography.hazmat.primitives import serialization

    _SIGNING_DIR.mkdir(parents=True, exist_ok=True)
    key_path = _SIGNING_DIR / "signing.key"
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem)
    key_path.chmod(0o600)
    pub_path = _SIGNING_DIR / "signing.pub"
    pub_bytes = private_key.public_key().public_bytes_raw()
    pub_path.write_text(base64.b64encode(pub_bytes).decode() + "\n")
    pub_path.chmod(0o644)


def cmd_gen_key(args):
    """Generate a new Ed25519 signing key for lock file signing."""
    priv, pub_bytes = _generate_signing_key()
    _save_signing_key(priv)
    fingerprint = _compute_fingerprint(pub_bytes)
    console.print("[green]Ed25519 signing key generated[/green]")
    console.print(f"  Public key fingerprint: [cyan]{fingerprint}[/cyan]")
    console.print(f"  Keys stored in: [cyan]{_SIGNING_DIR}[/cyan]")
    console.print("  signing.key — private key (DO NOT SHARE)")
    console.print("  signing.pub  — public key (share for verification)")
    return 0


def cmd_show_key(args):
    """Display the current public signing key."""
    result = _load_signing_key()
    if result is None:
        console.print("[red]No signing key found.[/red]")
        console.print(f"  Run [cyan]udr auth gen-key[/cyan] to create one at {_SIGNING_DIR}")
        return 1
    _, pub_bytes = result
    fingerprint = _compute_fingerprint(pub_bytes)
    table = Table(title="Current Signing Key", box=box.ROUNDED)
    table.add_column("Property", style="bold")
    table.add_column("Value")
    table.add_row("Algorithm", "Ed25519")
    table.add_row("Public Key (base64)", base64.b64encode(pub_bytes).decode())
    table.add_row("Fingerprint (SHA-256)", fingerprint)
    table.add_row("Key directory", str(_SIGNING_DIR))
    console.print(table)
    return 0


def _compute_fingerprint(pub_bytes: bytes) -> str:
    """Compute SHA-256 fingerprint of the public key, hex-encoded."""
    import hashlib

    return hashlib.sha256(pub_bytes).hexdigest()[:16]


def cmd_auth(args):
    """Manage API keys and signing keys — create, revoke, list, gen-key, show-key."""
    if args.auth_action == "gen-key":
        return cmd_gen_key(args)
    if args.auth_action == "show-key":
        return cmd_show_key(args)

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
