"""Пипо Алексей — запуск приложения.

По умолчанию открывается собственное окно (WebView2 — движок Edge, встроенный в Windows),
внутри работает локальный сервер на 127.0.0.1. Закрыли окно — приложение завершилось;
служба запрета при этом продолжает работать сама по себе.

    PipoAlexey.exe                # окно приложения (попросит права администратора)
    PipoAlexey.exe --browser      # вместо окна — обычный браузер
    PipoAlexey.exe --server-only  # только сервер (для разработки фронта)
    PipoAlexey.exe --no-admin     # без повышения прав (только просмотр)
"""
from __future__ import annotations

import argparse
import ctypes
import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from app import winutil
from app.settings import DATA_DIR, FROZEN

DEFAULT_PORT = 47800
TITLE = "Пипо Алексей"
log = logging.getLogger("pipo")


def setup_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(DATA_DIR / "pipo.log", encoding="utf-8")]
    if sys.stderr is not None:  # в оконной сборке консоли нет
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)


def relaunch_as_admin() -> bool:
    # python.exe main.py … — передаём и сам скрипт; PipoAlexey.exe … — только аргументы
    params = subprocess.list2cmdline(sys.argv[1:] if FROZEN else sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    return rc > 32


def free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int):
    """uvicorn в фоновом потоке; возвращает объект сервера, чтобы потом его остановить."""
    import uvicorn
    from app.api import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, thread


def message_box(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10)


def open_window(url: str) -> bool:
    """Окно на WebView2. False — если WebView2 недоступен (тогда откроем браузер)."""
    try:
        import webview
    except ImportError:
        log.warning("pywebview не установлен")
        return False
    try:
        webview.create_window(TITLE, url, width=1360, height=900, min_size=(960, 640),
                              background_color="#141415", text_select=True)
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(DATA_DIR / "webview"))
        return True
    except Exception:  # noqa: BLE001 — нет WebView2 Runtime и т.п.
        log.exception("не удалось открыть окно WebView2")
        return False


def open_edge_app(url: str) -> subprocess.Popen | None:
    """Запасной вариант: Edge в режиме приложения — отдельное окно без адресной строки."""
    for edge in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                 Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")):
        if edge.exists():
            return subprocess.Popen([str(edge), f"--app={url}", f"--user-data-dir={DATA_DIR / 'edge-app'}",
                                     "--window-size=1360,900"])
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-admin", action="store_true")
    ap.add_argument("--browser", action="store_true", help="открыть в обычном браузере вместо окна")
    ap.add_argument("--server-only", "--no-browser", dest="server_only", action="store_true")
    args = ap.parse_args()

    if not args.no_admin and not winutil.is_admin():
        if relaunch_as_admin():
            return
        # отказ от UAC — продолжаем в режиме просмотра

    setup_logging()
    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    try:
        server, thread = start_server(port)
    except Exception as e:  # noqa: BLE001
        log.exception("сервер не запустился")
        message_box(f"Не удалось запустить сервер: {e}")
        return
    log.info("UI: %s", url)

    if args.server_only:
        print(f"Пипо Алексей: {url}")
        thread.join()
        return

    if args.browser:
        winutil.open_url_unelevated(url)
        thread.join()
        return

    if not open_window(url):
        proc = open_edge_app(url)
        if proc:
            proc.wait()  # закрыли окно — выходим
        else:
            winutil.open_url_unelevated(url)
            thread.join()
    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    main()
