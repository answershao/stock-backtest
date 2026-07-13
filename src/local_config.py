from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_LOCAL_CONFIG_PATH = "config.local.json"


def load_local_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"本地配置文件格式错误: {config_path} ({exc})") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"本地配置文件必须是 JSON 对象: {config_path}")
    return data
