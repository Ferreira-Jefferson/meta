"""Cria o journal.sqlite a partir do schema."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from journal.writer import init_db


def main() -> None:
    init_db()
    print("journal.sqlite pronto em db/")


if __name__ == "__main__":
    main()
