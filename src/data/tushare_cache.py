from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class TushareDataCache:
    root_dir: Path
    cache_only: bool = True

    def load_or_fetch(
        self,
        *,
        dataset: str,
        key_parts: list[str],
        fetcher: Callable[[], pd.DataFrame],
    ) -> pd.DataFrame:
        path = self._build_path(dataset=dataset, key_parts=key_parts)
        if path.exists():
            return pd.read_csv(path)
        if self.cache_only:
            raise FileNotFoundError(f"缓存缺失: {path}")

        frame = fetcher()
        if frame is None:
            frame = pd.DataFrame()
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return frame.copy()

    def read(self, *, dataset: str, key_parts: list[str]) -> pd.DataFrame | None:
        path = self._build_path(dataset=dataset, key_parts=key_parts)
        if not path.exists():
            return None
        return pd.read_csv(path)

    def write(self, *, dataset: str, key_parts: list[str], frame: pd.DataFrame) -> Path:
        path = self._build_path(dataset=dataset, key_parts=key_parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return path

    def _build_path(self, *, dataset: str, key_parts: list[str]) -> Path:
        safe_parts = [_sanitize_path_part(part) for part in key_parts]
        filename = "__".join(safe_parts) + ".csv"
        return self.root_dir / dataset / filename


def _sanitize_path_part(value: str) -> str:
    safe = value.strip().replace("/", "-").replace("\\", "-").replace(":", "-").replace("*", "-")
    safe = safe.replace("?", "-").replace('"', "-").replace("<", "-").replace(">", "-").replace("|", "-")
    return safe or "empty"
