"""Смена движка: Flowseal (winws.exe) ⇄ zapret2 (winws2.exe).

Оба движка ставятся одной службой `zapret` (так делают service.bat обеих сборок) и
используют один драйвер WinDivert, поэтому одновременно работает только один.
Переключение: остановить всё вместе с драйвером, перенести настройки пользователя
в папку нового движка, наложить сплит и перенастроить службу на стратегию нового движка.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from . import settings, split, zapret

Log = Callable[..., None]

# что принадлежит пользователю, а не сборке: игровой фильтр и ручные подсети игровых профилей
_CARRY = ["utils/game_filter.enabled"]


class SwitchError(RuntimeError):
    pass


def remember_strategy(engine: str, strategy: str) -> None:
    saved = dict(settings.load().get("strategies") or {})
    saved[engine] = strategy
    settings.save({"strategies": saved})


def pick_strategy(engine: str, zdir: Path, current: str | None) -> str | None:
    """Стратегия для движка: прошлая выбранная → та же по имени → первая по списку."""
    names = zapret.list_strategies(zdir)
    for cand in ((settings.load().get("strategies") or {}).get(engine), current):
        if cand and cand in names:
            return cand
    return names[0] if names else None


def carry_user_files(src: Path, dst: Path) -> list[str]:
    """Копируем настройки пользователя, которых в новой папке ещё нет (своё не затираем)."""
    rels = list(_CARRY)
    rels += [f"lists/{f.name}" for f in (src / "lists").glob("ipset-*.txt")
             if not f.stem[len("ipset-"):].startswith(("all", "exclude"))]
    done = []
    for rel in rels:
        s, d = src / rel, dst / rel
        if s.is_file() and not d.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            done.append(rel)
    return done


def switch(engine: str, log: Log) -> dict:
    if engine not in zapret.ENGINES:
        raise SwitchError("движок: flowseal или zapret2")
    eng = zapret.ENGINES[engine]
    old_id = settings.engine()
    old_dir, new_dir = settings.zapret_dir(), settings.engine_dir(engine)
    if engine == old_id:
        return {"engine": engine, "strategy": zapret.installed_strategy(), "started": False}
    if not zapret.winws_exe_of(new_dir, eng).is_file():
        raise SwitchError(f"{eng.title} не установлен: нет {zapret.winws_exe_of(new_dir, eng)}. "
                          "Установите его во вкладке «Обновления» или укажите папку в «Настройках»")

    state = zapret.service_state()
    current = zapret.installed_strategy() if state is not None else None
    was_running = state in ("running", "start_pending", "continue_pending")
    # всё, что может не получиться без последствий, — до остановки запрета
    strategy = pick_strategy(engine, new_dir, current) if state is not None else None
    if state is not None and not strategy:
        raise SwitchError(f"в {new_dir} нет ни одной стратегии general*.bat")
    if current:
        remember_strategy(old_id, current)

    log("Останавливаю запрет и драйвер WinDivert")
    zapret.stop_all(stop_driver=True)
    ipset = zapret.ipset_mode(old_dir)
    carried = carry_user_files(old_dir, new_dir)
    if carried:
        log("Перенесено в папку нового движка: " + ", ".join(carried))
    settings.save({"engine": engine})
    try:
        try:
            split.apply(new_dir, ipset_mode=ipset, adopt=False)  # режим IPSet — как был у прежнего движка
            log("Сплит-правила и игровые профили применены к спискам нового движка")
        except Exception as e:  # noqa: BLE001 — сплит не должен мешать сменить движок
            log(f"Не удалось применить сплит-правила: {e}", "warn")
        if strategy:
            zapret.install_service(new_dir, strategy, start=was_running)
            remember_strategy(engine, strategy)
            log(f"Служба перенастроена на «{strategy}»" + (" и запущена" if was_running else ""))
    except Exception as e:
        # новый движок не встал — возвращаем прежний, как был, а не оставляем пользователя без запрета
        log(f"Не получилось: {e}. Возвращаю {zapret.ENGINES[old_id].title}", "error")
        settings.save({"engine": old_id})
        if current:
            try:
                zapret.install_service(old_dir, current, start=was_running)
            except Exception as e2:  # noqa: BLE001
                log(f"Вернуть прежнюю службу тоже не вышло: {e2}", "error")
        raise SwitchError(f"не удалось включить {eng.title}: {e}") from e
    log(f"Движок: {eng.title}", "ok")
    return {"engine": engine, "strategy": strategy, "started": bool(strategy) and was_running}
