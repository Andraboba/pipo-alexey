"""TG WS Proxy (Flowseal/tg-ws-proxy) — локальный MTProto-прокси для Telegram Desktop."""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from . import settings, winutil

APP_NAME = "TgWsProxy"
EXE_NAME = "TgWsProxy.exe"
VERSION_FILE = "tgwsproxy_version.txt"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def find_exe() -> Path | None:
    s = settings.load()
    candidates = []
    if s.get("tg_exe"):
        candidates.append(Path(s["tg_exe"]))
    candidates += [
        Path(s["zapret_dir"]) / EXE_NAME,
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / APP_NAME / EXE_NAME,
        Path(os.environ.get("USERPROFILE", "")) / "Downloads" / EXE_NAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def config_dir(exe: Path | None) -> Path:
    # portable-режим самого приложения: папка TgWsProxy_data рядом с exe
    if exe and (exe.parent / "TgWsProxy_data").is_dir():
        return exe.parent / "TgWsProxy_data"
    return Path(os.environ.get("APPDATA", Path.home())) / APP_NAME


def read_config(exe: Path | None) -> dict:
    try:
        return json.loads((config_dir(exe) / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def local_version(exe: Path | None) -> str | None:
    if not exe:
        return None
    try:
        v = (exe.parent / VERSION_FILE).read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    v = winutil.file_version(exe)
    if v:
        return "v" + ".".join(v.split(".")[:3])
    return None


def write_version(exe: Path, version: str) -> None:
    settings.write_text_atomic(exe.parent / VERSION_FILE, version)


def proxy_link(cfg: dict) -> str | None:
    secret = cfg.get("secret")
    if not secret:
        return None
    host = cfg.get("host") or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"tg://proxy?server={host}&port={cfg.get('port', 1443)}&secret=dd{secret}"


def port_open(host: str, port: int) -> bool:
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    try:
        with socket.create_connection((host, int(port)), timeout=0.4):
            return True
    except OSError:
        return False


def autostart_enabled(exe: Path | None) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val = str(winreg.QueryValueEx(k, APP_NAME)[0]).strip()
    except OSError:
        return False
    return bool(val) and (exe is None or val.strip('"').lower() == str(exe).lower())


def set_autostart(exe: Path, enabled: bool) -> None:
    """Тот же формат, что пишет само приложение: значение TgWsProxy = "путь\\TgWsProxy.exe"."""
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def running(exe: Path | None) -> bool:
    return winutil.process_running(exe.name if exe else EXE_NAME)


def start(exe: Path) -> None:
    if not running(exe):
        winutil.launch_unelevated(exe)


def stop(exe: Path | None) -> None:
    winutil.kill_process(exe.name if exe else EXE_NAME)


def status() -> dict:
    exe = find_exe()
    cfg = read_config(exe)
    host, port = cfg.get("host", "127.0.0.1"), cfg.get("port", 1443)
    return {
        "installed": exe is not None,
        "exe": str(exe) if exe else None,
        "version": local_version(exe),
        "running": running(exe),
        "listening": port_open(host, port),
        "host": host,
        "port": port,
        "link": proxy_link(cfg),
        "autostart": autostart_enabled(exe),
        "config_dir": str(config_dir(exe)),
    }
