"""Write the FastAPI OpenAPI schema to apps/api/openapi.json (input for openapi-typescript)."""

from __future__ import annotations

import json
from pathlib import Path

from apps.api.main import create_app

OUT = Path(__file__).resolve().parents[1] / "apps" / "api" / "openapi.json"

if __name__ == "__main__":
    schema = create_app(lambda: None).openapi()
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(OUT.parents[2])} ({len(schema['paths'])} paths)")
