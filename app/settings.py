"""Пути и настройки приложения."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

FROZEN = bool(getattr(sys, "frozen", False))  # запущены из PipoAlexey.exe (PyInstaller)
PROJECT_DIR = Path(__file__).resolve().parent.parent
# в exe интерфейс лежит внутри сборки, а данные — в папке data рядом с exe
WEB_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR)) / "web"
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else PROJECT_DIR
DATA_DIR = Path(os.environ.get("PIPO_DATA_DIR") or APP_DIR / "data")

DEFAULTS: dict[str, Any] = {
    "zapret_dir": r"C:\Zapret",
    # второй движок — zapret2 (winws2.exe) в сборке kinlay0; работает только один из двух
    "zapret2_dir": r"C:\Zapret2",
    "engine": "flowseal",  # flowseal | zapret2
    # последняя стратегия каждого движка — чтобы при переключении вернуть свою
    "strategies": {},
    # None — искать TgWsProxy.exe рядом с запретом
    "tg_exe": None,
}

_lock = threading.Lock()


def settings_file() -> Path:
    return DATA_DIR / "settings.json"


def load() -> dict[str, Any]:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(settings_file().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if os.environ.get("PIPO_ZAPRET_DIR"):
        data["zapret_dir"] = os.environ["PIPO_ZAPRET_DIR"]
    return data


def save(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        data.update({k: v for k, v in patch.items() if k in DEFAULTS})
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_text_atomic(settings_file(), json.dumps(data, indent=2, ensure_ascii=False))
        return data


ENGINE_DIR_KEYS = {"flowseal": "zapret_dir", "zapret2": "zapret2_dir"}


def engine() -> str:
    e = load().get("engine")
    return e if e in ENGINE_DIR_KEYS else "flowseal"


def engine_dir(engine_id: str) -> Path:
    return Path(load()[ENGINE_DIR_KEYS[engine_id]])


def zapret_dir() -> Path:
    """Папка активного движка: с ней работают служба, сплит, подбор и игры."""
    return engine_dir(engine())


def write_text_atomic(path: Path, text: str) -> None:
    """UTF-8 без BOM, LF. Пишем во временный файл и подменяем — без полуфайлов."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.pipo-tmp")  # свой у каждого потока
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
