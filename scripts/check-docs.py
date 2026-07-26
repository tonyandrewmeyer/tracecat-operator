# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Enforces that docs/configuration.md matches charmcraft.yaml config options.

Usage:
    uv run python scripts/check-docs.py          # check (exit 1 on drift)
    uv run python scripts/check-docs.py --write   # regenerate the table
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML required: uv pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
CHARMCRAFT = ROOT / "charmcraft.yaml"
DOCS = ROOT / "docs" / "configuration.md"
TABLE_START = "<!-- This table is enforced against charmcraft.yaml"
TABLE_END = "## Secrets"


def load_config() -> list[tuple[str, str, str, str]]:
    """Read the charm config options from charmcraft.yaml as table rows."""
    data = yaml.safe_load(CHARMCRAFT.read_text())
    options = data.get("config", {}).get("options", {})
    rows = []
    for key, spec in options.items():
        typ = spec.get("type", "string")
        default = spec.get("default", "")
        desc = " ".join(str(spec.get("description", "")).split())
        if isinstance(default, bool):
            default = str(default).lower()
        rows.append((key, typ, str(default), desc))
    return rows


def render_table(rows: list[tuple[str, str, str, str]]) -> str:
    """Render the config rows as a Markdown table."""
    lines = [
        "| Key | Type | Default | Description |",
        "|---|---|---|---|",
    ]
    for key, typ, default, desc in rows:
        default = default.replace("|", "\\|") if default else "``"
        lines.append(f"| `{key}` | {typ} | `{default}` | {desc} |")
    return "\n".join(lines)


def main() -> int:
    """Check the README config table matches charmcraft.yaml, or regenerate it."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="regenerate the table")
    args = parser.parse_args()

    rows = load_config()
    table = render_table(rows)
    content = DOCS.read_text()

    start_idx = content.find(TABLE_START)
    if start_idx == -1:
        print("configuration.md table marker not found", file=sys.stderr)
        return 1
    # Move to the line after the marker comment.
    start_idx = content.index("\n", start_idx) + 1
    end_idx = content.find("\n## Secrets", start_idx)
    if end_idx == -1:
        end_idx = len(content)

    current = content[start_idx:end_idx].strip()
    if current == table.strip():
        print("configuration.md is in sync with charmcraft.yaml")
        return 0

    if args.write:
        new_content = content[:start_idx] + table + "\n\n" + content[end_idx:]
        DOCS.write_text(new_content)
        print("configuration.md regenerated")
        return 0

    print("configuration.md is out of sync with charmcraft.yaml:", file=sys.stderr)
    print(f"  charmcraft.yaml has {len(rows)} config options", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
