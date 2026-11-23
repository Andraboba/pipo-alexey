"""Фоновые задачи (подбор, обновления) с логом, который UI опрашивает."""
from __future__ import annotations

import copy
import threading
import time
import traceback
import uuid
from typing import Callable


class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.state = "running"  # running | done | error
        self.log: list[dict] = []
        self.progress: float | None = None
        self.result = None
        self.started = time.time()
        self.cancelled = False  # задача сама проверяет флаг между шагами

    def say(self, text: str, level: str = "info") -> None:
        self.log.append({"t": time.time(), "level": level, "text": text})

    def to_dict(self) -> dict:
        """Снимок для API. Поток задачи в это время дописывает log и result — отдаём копию, а не живые объекты."""
        for _ in range(10):
            try:
                return copy.deepcopy({"id": self.id, "kind": self.kind, "state": self.state, "log": self.log,
                                      "progress": self.progress, "result": self.result, "cancelled": self.cancelled})
            except RuntimeError:  # «dictionary changed size during iteration» — задача как раз что-то дописала
                time.sleep(0.01)
        return {"id": self.id, "kind": self.kind, "state": self.state, "log": list(self.log),
                "progress": self.progress, "result": None, "cancelled": self.cancelled}


_jobs: dict[str, Job] = {}
_busy = threading.Lock()


class Busy(RuntimeError):
    pass


def start(kind: str, fn: Callable[[Job], object]) -> Job:
    """Одна тяжёлая задача за раз — два параллельных обновления нам ни к чему."""
    if not _busy.acquire(blocking=False):
        raise Busy("уже выполняется другая операция")
    job = Job(kind)
    _jobs[job.id] = job

    def runner():
        try:
            job.result = fn(job)
            job.state = "done"
        except Exception as e:  # noqa: BLE001 — показываем пользователю любую ошибку
            job.say(f"Ошибка: {e}", "error")
            job.say(traceback.format_exc(limit=3), "debug")
            job.state = "error"
        finally:
            _busy.release()

    threading.Thread(target=runner, daemon=True, name=f"job-{kind}").start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def current() -> Job | None:
    running = [j for j in list(_jobs.values()) if j.state == "running"]
    return running[-1] if running else None


def shutdown(timeout: float) -> bool:
    """Выход из приложения: попросить задачу остановиться и дождаться, пока она вернёт всё как было."""
    job = current()
    if not job:
        return True
    job.cancelled = True
    end = time.monotonic() + timeout
    while job.state == "running" and time.monotonic() < end:
        time.sleep(0.2)
    return job.state != "running"
