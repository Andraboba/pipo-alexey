"""Фоновые задачи (обновления) с логом, который UI опрашивает."""
from __future__ import annotations

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
        return {"id": self.id, "kind": self.kind, "state": self.state, "log": self.log,
                "progress": self.progress, "result": self.result, "cancelled": self.cancelled}


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
    running = [j for j in _jobs.values() if j.state == "running"]
    return running[-1] if running else None
