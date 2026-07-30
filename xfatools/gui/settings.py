"""Persisted user preferences, stored as one small JSON file.

Deliberately not QSettings: a plain readable file in the user's AppData is
easier to inspect, reset and carry between machines, and it keeps the packaged
application free of registry writes.  No database, per the project's constraints.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_DIR_NAME = "XfaStudio"
SETTINGS_FILENAME = "settings.json"

#: Most recent source files remembered for the "recent" menu.
MAX_RECENT = 12


def config_dir() -> Path:
    """Per-user configuration directory, created on demand."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    target = base / APP_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


@dataclass
class Settings:
    """Everything the application remembers between runs."""

    theme: str = "system"  # "system" | "light" | "dark"
    language: str = ""  # "" means follow the operating system
    output_mode: str = "beside_source"  # "beside_source" | "custom"
    output_dir: str = ""
    concurrency: int = 0  # 0 means choose automatically
    window_geometry: str = ""
    recent_files: list[str] = field(default_factory=list)
    ocr_language: str = "ita+eng"
    max_pages: int = 100

    # -- persistence ------------------------------------------------------

    @classmethod
    def path(cls) -> Path:
        return config_dir() / SETTINGS_FILENAME

    @classmethod
    def load(cls) -> Settings:
        """Read the settings file, falling back to defaults on any problem.

        A corrupt or hand-edited file must never stop the application starting.
        """
        target = cls.path()
        if not target.exists():
            return cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()

        known = {f for f in cls.__dataclass_fields__}
        clean: dict[str, Any] = {k: v for k, v in data.items() if k in known}
        try:
            return cls(**clean)
        except TypeError:
            return cls()

    def save(self) -> None:
        """Write atomically, so an interrupted write cannot corrupt the file."""
        target = self.path()
        temporary = target.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
            )
            temporary.replace(target)
        except OSError:
            # Settings are a convenience; failing to save must not break the app.
            pass

    # -- helpers ----------------------------------------------------------

    def remember_file(self, path: str | Path) -> None:
        text = str(Path(path))
        if text in self.recent_files:
            self.recent_files.remove(text)
        self.recent_files.insert(0, text)
        del self.recent_files[MAX_RECENT:]

    def resolved_output_dir(self, source: Path) -> Path | None:
        """Where a result should go: ``None`` means next to the source file."""
        if self.output_mode == "custom" and self.output_dir:
            return Path(self.output_dir)
        return None

    def worker_count(self) -> int:
        if self.concurrency > 0:
            return self.concurrency
        return max(1, min(4, (os.cpu_count() or 2)))
