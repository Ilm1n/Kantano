from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parents[1]
FRONTEND_OPENAPI_PATH = ROOT_DIR / "frontend" / "light-task-frontend" / "openapi.json"


def main() -> None:
    sys.path.insert(0, str(BACKEND_DIR))

    from src.main import main_app

    schema = main_app.openapi()
    FRONTEND_OPENAPI_PATH.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"OpenAPI schema exported to: {FRONTEND_OPENAPI_PATH}")
    print("Next step: cd ../../frontend/light-task-frontend && pnpm gen:api")


if __name__ == "__main__":
    main()
