from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.site.build_static import (  # noqa: E402
    DEFAULT_DOCS_DIR,
    DEFAULT_EXPORT_DIR,
    build_static_site,
)
from src.utils.db import DEFAULT_DB_PATH  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Signal League site.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()

    pages = build_static_site(
        db_path=args.db,
        docs_dir=args.docs_dir,
        export_dir=args.export_dir,
    )

    for page in pages.values():
        print(f"Wrote {page}")


if __name__ == "__main__":
    main()
