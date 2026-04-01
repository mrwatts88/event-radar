from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_files(*paths: Path) -> None:
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key.strip(), value)
