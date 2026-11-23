"""Временно убрать запрет с дороги и гарантированно вернуть всё как было.

    with suspended(zdir, job.say, ipset="any"):
        ...  # служба и winws остановлены, IPSet в режиме «Все»

Пользуются подбор стратегий и обновление zapret. Внутри — снимок «как было»,
возврат по шагам (сбой одного шага не отменяет остальные) и журнал на диске:
если приложение закрыли посреди задачи, recover() при следующем старте доделает возврат.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator

from . import split, winutil, zapret
from .settings import DATA_DIR, write_text_atomic

Log = Callable[..., None]  # (text, level="info")

# служба была запущена или как раз запускалась — после паузы запускаем снова
_RUNNING = ("running", "start_pending", "continue_pending")


@dataclass
class Snapshot:
    zdir: str
    service: str | None  # None — служба не установлена
    bat_winws: bool  # winws.exe был запущен через .bat: вернуть его можем только просьбой к пользователю
    ipset: str

    @property
    def service_was_running(self) -> bool:
        return self.service in _RUNNING


def _journal() -> Path:
    return DATA_DIR / "restore.json"


def take(zdir: Path) -> Snapshot:
    service = zapret.service_state()
    bat = service not in _RUNNING and winutil.process_running("winws.exe")
    return Snapshot(zdir=str(zdir), service=service, bat_winws=bat, ipset=zapret.ipset_mode(zdir))


def restore(snap: Snapshot, log: Log) -> bool:
    """Вернуть как было. True — всё получилось; ошибки шагов пишутся в log, а не бросаются."""
    zdir = Path(snap.zdir)
    ok = True
    try:
        if zapret.ipset_mode(zdir) != snap.ipset:
            split.set_ipset_mode(zdir, snap.ipset)
            log("Режим IPSet возвращён")
    except Exception as e:  # noqa: BLE001 — следующий шаг важнее
        ok = False
        log(f"Не удалось вернуть режим IPSet: {e}", "error")
    if snap.service_was_running:
        try:
            zapret.start_service()
            log("Служба запрета снова запущена")
        except Exception as e:  # noqa: BLE001
            ok = False
            log(f"Не удалось вернуть службу: {e}", "error")
    if snap.bat_winws:
        log("winws.exe был запущен через .bat — запустите его заново", "warn")
    return ok


@contextmanager
def suspended(zdir: Path, log: Log, *, ipset: str | None = None, stop_driver: bool = False) -> Iterator[Snapshot]:
    snap = take(zdir)
    write_text_atomic(_journal(), json.dumps(asdict(snap), ensure_ascii=False))
    try:
        zapret.stop_all(stop_driver=stop_driver)
        if ipset and ipset != snap.ipset:
            split.set_ipset_mode(zdir, ipset)
        yield snap
    finally:
        if restore(snap, log):
            _journal().unlink(missing_ok=True)


def pending() -> bool:
    return _journal().exists()


def recover(log: Log) -> bool:
    """При старте: прошлый запуск не успел вернуть запрет — возвращаем. True, если было что возвращать."""
    try:
        snap = Snapshot(**json.loads(_journal().read_text(encoding="utf-8")))
    except FileNotFoundError:
        return False
    except (OSError, ValueError, TypeError) as e:
        log(f"Журнал восстановления не читается, пропускаю: {e}", "warn")
        _journal().unlink(missing_ok=True)
        return False
    log("Прошлый запуск не успел вернуть запрет после подбора или обновления — возвращаю")
    try:
        zapret.stop_all()  # winws прерванного подбора мог остаться жить — служба рядом с ним не нужна
    except Exception as e:  # noqa: BLE001
        log(f"Не удалось остановить оставшийся winws.exe: {e}", "warn")
    restore(snap, log)
    _journal().unlink(missing_ok=True)  # повторять бесконечно при каждом старте не будем
    return True
