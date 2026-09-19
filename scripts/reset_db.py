"""Drop and recreate every table. Local development only."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import Base, create_all, engine  # noqa: E402


def main() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    import app.models  # noqa: F401  (registers the mappers)

    Base.metadata.drop_all(bind=engine)
    create_all()
    print(f"Reset {len(Base.metadata.tables)} tables at {settings.db_path}")


if __name__ == "__main__":
    main()
