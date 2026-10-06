from __future__ import annotations

import configparser
import re
from pathlib import Path


class JFlashProjectError(ValueError):
    """Raised when a J-Flash project does not contain a usable MCU name."""


def parse_jflash_project(path: Path) -> str:
    """Return the MCU name selected in a J-Flash project file."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1252")
    except OSError as exc:
        raise JFlashProjectError(f"\u65e0\u6cd5\u8bfb\u53d6 J-Flash \u5de5\u7a0b\uff1a{exc}") from exc

    section_start = re.search(r"(?m)^\s*\[[^\]]+\]\s*$", text)
    if section_start is None:
        raise JFlashProjectError("J-Flash \u5de5\u7a0b\u4e2d\u627e\u4e0d\u5230\u914d\u7f6e\u6bb5\u3002")
    text = text[section_start.start():]

    project = configparser.ConfigParser(interpolation=None, strict=False)
    project.optionxform = str
    try:
        project.read_string(text)
    except configparser.Error as exc:
        raise JFlashProjectError("J-Flash \u5de5\u7a0b\u683c\u5f0f\u65e0\u6cd5\u89e3\u6790\u3002") from exc

    if not project.has_section("CPU"):
        raise JFlashProjectError("J-Flash \u5de5\u7a0b\u4e2d\u627e\u4e0d\u5230 [CPU] \u914d\u7f6e\u6bb5\u3002")

    for key in ("ChipName", "DeviceName", "MCU", "TargetDevice"):
        if project.has_option("CPU", key):
            chip_name = project.get("CPU", key).strip().strip('"').strip("'").strip()
            if chip_name:
                return chip_name

    raise JFlashProjectError("J-Flash \u5de5\u7a0b\u4e2d\u627e\u4e0d\u5230 MCU \u914d\u7f6e\u3002")