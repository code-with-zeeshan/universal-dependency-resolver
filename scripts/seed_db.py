#!/usr/bin/env python3
"""Seed the database with sample packages for development/testing.

Usage:
    python scripts/seed_db.py                  # use default DB
    python scripts/seed_db.py --db sqlite:///custom.db
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.compatibility_db import CompatibilityDB

SAMPLE_PACKAGES = [
    # (name, ecosystem, version, description)
    ("numpy", "pypi", "1.26.2", "Scientific computing with Python"),
    ("pandas", "pypi", "2.1.4", "Data analysis toolkit"),
    ("requests", "pypi", "2.31.0", "HTTP library"),
    ("flask", "pypi", "3.0.0", "Web framework"),
    ("torch", "pypi", "2.1.2", "PyTorch deep learning framework"),
    ("tensorflow", "pypi", "2.15.0", "TensorFlow deep learning framework"),
    ("transformers", "pypi", "4.36.2", "HuggingFace Transformers"),
    ("react", "npm", "18.2.0", "UI library"),
    ("express", "npm", "4.18.2", "Web framework for Node.js"),
    ("serde", "crates", "1.0.193", "Serialization framework for Rust"),
    ("tokio", "crates", "1.35.1", "Async runtime for Rust"),
]


def seed(conflict_rules: bool = True):
    db = CompatibilityDB()
    count = 0

    for name, ecosystem, version, description in SAMPLE_PACKAGES:
        try:
            db.add_package(
                name,
                ecosystem,
                {
                    "version": version,
                    "description": description,
                    "versions": [{"version": version}],
                },
            )
            count += 1
            print(f"  ✓ {name} ({ecosystem}) v{version}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    if conflict_rules:
        try:
            db.add_conflict_rule(
                "torch",
                ">=2.0.0",
                "tensorflow",
                "<2.16.0",
                "incompatible",
                "PyTorch 2.x and TensorFlow 2.x CUDA conflicts",
                severity="warning",
                resolution="Use separate environments or Docker",
            )
            print("  ✓ conflict rule: torch ↔ tensorflow (CUDA)")
        except Exception as e:
            print(f"  ✗ conflict rule: {e}")

    print(f"\nSeeded {count} packages.")


def main():
    parser = argparse.ArgumentParser(description="Seed dev database")
    parser.add_argument("--db", help="Database URL (default: from settings)")
    args = parser.parse_args()

    if args.db:
        import os

        os.environ["DATABASE_URL"] = args.db

    seed()


if __name__ == "__main__":
    main()
