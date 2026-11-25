"""JSON Lines reading shared by the pipeline and the app (stdlib only, so the app image stays slim)."""

import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    # Split on "\n" only: str.splitlines() also breaks on U+2028 etc., which appear unescaped inside abstracts.
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]
