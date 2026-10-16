"""Compatibility wrapper — the real implementation is ``app.cli``.

Kept because docs and muscle memory reference this path:

    docker compose exec api python scripts/create_admin.py --username admin
    docker compose exec api python -m app.cli create-admin --username admin

Both run the same code. One behaviour change versus the original script: it no
longer prints a generated password when stdin is not a TTY. Non-interactive
bootstrap must pipe the password explicitly with ``--password-stdin``, so a
secret can never end up in a build log or CI output.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["create-admin", *sys.argv[1:]]))
