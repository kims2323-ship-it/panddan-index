"""프로젝트 .env 로더. 셸 환경변수 우선, os.environ 을 덮어쓰지 않고, 템플릿 문구는 미설정 취급."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PLACEHOLDER = "여기에_키"
_file_vals: dict = {}


def _load() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        _file_vals[k.strip()] = v.strip().strip("'\"")


_load()


def get(name: str) -> str:
    v = os.environ.get(name) or _file_vals.get(name, "")
    return "" if _PLACEHOLDER in v else v
