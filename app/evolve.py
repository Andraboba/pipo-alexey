"""Эволюция стратегий zapret2: приложение само ищет обход под вашего провайдера.

Стратегия для TLS (то, что winws2 делает с ClientHello) — это цепочка шагов
--lua-desync: 0–2 фейка и в конце не больше одного «разрезателя»:

    fake:blob=tls_google:repeats=6:tcp_md5  →  multisplit:pos=midsld

Шаги и их параметры — «гены». Генетический алгоритм:
  1. первое поколение — TLS-часть всех готовых стратегий сборки плюс случайные;
  2. каждый кандидат запускается в winws2 на пару секунд и проверяется на целях
     подбора (те же проверки, что в scan.py);
  3. лучшие остаются, из них скрещиванием и мутациями растут новые;
  4. лучших перепроверяем повторно — сеть шумит, случайная удача не должна победить.

Оценка — как в подборе: заблокированные без запрета цели чинить, открытые не ломать.
Пропал интернет — ждём, а не записываем всем кандидатам ноль. Состояние пишется на
диск после каждого поколения: можно остановить и продолжить следующей ночью.

    evolve(job, evaluate=..., ...)          # движок, без сети и winws — для тестов
    run_evolve(job, zdir, targets, hours)   # настоящий запуск
    save_bat(zdir, steps)                   # найденное — в general (PIPO EVO N).bat
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import scan, suspend, winutil, zapret
from .jobs import Job
from .settings import write_text_atomic

class EvolveError(RuntimeError):
    pass


# ---------- гены ----------

# фейки из lua/blobs.lua сборки kinlay0 (fake_default_tls встроен в winws2)
FAKE_BLOBS = ["fake_default_tls", "tls_google", "tls_sferum", "tls_4pda", "tls_onetrust", "tls_teamspeak",
              "tls_5ka", "tls_mail", "tls_steamchat", "tls_retext", "tls_firpo", "stun", "stun2"]
# как сделать, чтобы фейк увидел DPI, но не принял сервер
FOOLS = ["", "tcp_md5", "tcp_seq=-10000", "tcp_ack=-66000", "tcp_ts=-600000", "badsum",
         "ip_autottl=-1,3-20", "ip_autottl=-2,3-20"]
# sni российских сайтов — их ТСПУ пропускает без «заморозки 16–20 КБ»: фейк с таким именем может
# сбить DPI с толку на зарубежных хостингах (идея «белых SNI» из dpi-detector)
TLS_MODS = ["", "rnd", "rndsni", "rnd,dupsid", "rnd,dupsid,sni=www.google.com",
            "rnd,dupsid,sni=vk.com", "rnd,dupsid,sni=ya.ru", "rnd,dupsid,sni=gosuslugi.ru"]
REPEATS = [1, 2, 3, 4, 6, 8, 11]
MULTI_POS = ["1", "2", "3", "host", "host+1", "midsld", "sniext+1", "1,midsld", "2,midsld", "3,sniext+1",
             "sniext+1,midsld", "2,host+2", "1,sniext+1,host+1,midsld"]
SINGLE_POS = ["1", "2", "midsld", "host+1", "sniext+1"]
SEQOVL = ["", "1", "336", "568", "661", "681"]
PATTERNS = ["tls_google", "tls_4pda", "tls_sferum", "tls_teamspeak", "stun2"]
HOSTS = ["www.google.com", "vk.com", "ya.ru", "mail.ru"]

SPACE: dict[str, dict[str, list]] = {
    "fake": {"blob": FAKE_BLOBS, "repeats": REPEATS, "fool": FOOLS, "tls_mod": TLS_MODS},
    "multisplit": {"pos": MULTI_POS, "seqovl": SEQOVL, "seqovl_pattern": PATTERNS},
    "multidisorder": {"pos": MULTI_POS},
    "fakedsplit": {"pos": SINGLE_POS, "repeats": REPEATS, "fool": FOOLS},
    "fakeddisorder": {"pos": SINGLE_POS, "repeats": REPEATS, "fool": FOOLS},
    "hostfakesplit": {"host": HOSTS, "midhost": ["", "midsld"], "repeats": REPEATS, "fool": FOOLS},
}
TERMINALS = [f for f in SPACE if f != "fake"]  # режут оригинал — после них ничего не ставим
MAX_FAKES = 2
_FOOL_KEYS = ("tcp_md5", "tcp_seq", "tcp_ack", "tcp_ts", "badsum", "ip_ttl", "ip_autottl")
_ORDER = ["blob", "pos", "host", "midhost", "seqovl", "seqovl_pattern", "repeats", "fool", "tls_mod"]


@dataclass(frozen=True)
class Step:
    func: str
    genes: tuple[tuple[str, str], ...] = ()  # (имя, значение) в порядке _ORDER, без пустых
    extra: tuple[str, ...] = ()  # чужие аргументы из готовых стратегий — переносим как есть

    def get(self, name: str) -> str:
        return dict(self.genes).get(name, "")

    def with_gene(self, name: str, value) -> "Step":
        g = dict(self.genes)
        g[name] = str(value)
        return Step(self.func, _norm(g), self.extra)

    def __str__(self) -> str:
        parts = [self.func]
        for k, v in self.genes:
            if k == "fool":
                parts.append(v)  # tcp_md5 или tcp_seq=-10000 — уже готовый аргумент
            elif not (k == "repeats" and v == "1"):
                parts.append(f"{k}={v}")
        return ":".join(parts + list(self.extra))


def _norm(g: dict) -> tuple[tuple[str, str], ...]:
    g = {k: str(v) for k, v in g.items() if str(v) != ""}
    if "seqovl" not in g:
        g.pop("seqovl_pattern", None)  # узор без перекрытия ничего не значит
    return tuple((k, g[k]) for k in _ORDER if k in g)


def parse_step(text: str) -> Step | None:
    """'fake:blob=tls_google:repeats=6:tcp_md5' → Step. None — функция не из нашего набора."""
    func, *rest = text.split(":")
    if func not in SPACE:
        return None
    genes, extra = {}, []
    for tok in rest:
        key, _, val = tok.partition("=")
        if key in _FOOL_KEYS and "fool" not in genes:
            genes["fool"] = tok
        elif key in _ORDER and key != "fool" and val:
            genes[key] = val
        else:
            extra.append(tok)
    return Step(func, _norm(genes), tuple(extra))


Genome = tuple[Step, ...]


def key(g: Genome) -> str:
    return " → ".join(str(s) for s in g)


def valid(g: Genome) -> bool:
    fakes = [s for s in g if s.func == "fake"]
    terms = [s for s in g if s.func != "fake"]
    return bool(g) and len(fakes) <= MAX_FAKES and len(terms) <= 1 and (not terms or g[-1].func != "fake")


def random_step(func: str, rng: random.Random) -> Step:
    return Step(func, _norm({name: rng.choice(vals) for name, vals in SPACE[func].items()}))


def random_genome(rng: random.Random) -> Genome:
    while True:
        fakes = tuple(random_step("fake", rng) for _ in range(rng.choice([0, 1, 1, 2])))
        term = (random_step(rng.choice(TERMINALS), rng),) if rng.random() < 0.85 else ()
        g = fakes + term
        if valid(g):
            return g


def mutate(g: Genome, rng: random.Random) -> Genome:
    for _ in range(20):
        steps = list(g)
        op = rng.random()
        fakes = [i for i, s in enumerate(steps) if s.func == "fake"]
        term = steps[-1] if steps and steps[-1].func != "fake" else None
        if op < 0.55 and steps:  # поменять один ген
            i = rng.randrange(len(steps))
            names = list(SPACE[steps[i].func])
            name = rng.choice(names)
            steps[i] = steps[i].with_gene(name, rng.choice(SPACE[steps[i].func][name]))
        elif op < 0.7 and len(fakes) < MAX_FAKES:  # добавить фейк
            steps.insert(rng.randint(0, len(fakes)), random_step("fake", rng))
        elif op < 0.8 and fakes:  # убрать фейк
            steps.pop(rng.choice(fakes))
        elif op < 0.92:  # сменить или добавить разрезатель
            new = random_step(rng.choice(TERMINALS), rng)
            steps = steps[:-1] + [new] if term else steps + [new]
        elif term:  # убрать разрезатель
            steps.pop()
        out = tuple(steps)
        if valid(out) and out != g:
            return out
    return g


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    """Фейки одного родителя + разрезатель другого."""
    fa, ta = [s for s in a if s.func == "fake"], [s for s in a if s.func != "fake"]
    fb, tb = [s for s in b if s.func == "fake"], [s for s in b if s.func != "fake"]
    child = tuple((fa if rng.random() < 0.5 else fb) + (tb if rng.random() < 0.5 else ta))
    return child if valid(child) else a


# ---------- семена из готовых стратегий ----------

def tls_chain(args: list[str]) -> list[str]:
    """--lua-desync для ClientHello из профиля с доменами (как «domain tls» у kinlay0)."""
    profiles, cur = [], []
    for a in args:
        if a == "--new":
            profiles.append(cur)
            cur = []
        else:
            cur.append(a)
    profiles.append(cur)

    def chain(p: list[str]) -> list[str]:
        out, on = [], False
        for a in p:
            if a.startswith("--payload="):
                on = "tls_client_hello" in a.split("=", 1)[1].split(",")
            elif on and a.startswith("--lua-desync="):
                out.append(a.split("=", 1)[1])
        return out

    tls = [p for p in profiles if chain(p) and any(a.startswith("--filter-tcp=") and "443" in a for a in p)]
    named = [p for p in tls if any(a.replace('"', "") == "--name=domain tls" for a in p)]
    hosted = [p for p in tls if any(a.startswith("--hostlist=") for a in p)]
    best = (named or hosted or tls or [[]])[0]
    return chain(best)


def seeds_from(zdir: Path) -> dict[str, Genome]:
    """Имя стратегии → её TLS-цепочка (только те, что целиком из наших генов)."""
    out: dict[str, Genome] = {}
    seen = set()
    for name in zapret.list_strategies(zdir):
        try:
            args = zapret.build_args(zdir, name, zapret.GameFilter())
        except zapret.StrategyError:
            continue
        steps = [parse_step(s) for s in tls_chain(args)]
        g = tuple(steps)
        if steps and None not in steps and valid(g) and key(g) not in seen:
            seen.add(key(g))
            out[name] = g
    return out


# ---------- оценка ----------

@dataclass
class Cand:
    genome: Genome
    evals: list[dict[str, float]] = field(default_factory=list)  # по прогону: id цели → балл
    ms: list[int] = field(default_factory=list)
    invalid: bool = False  # winws2 не принял аргументы
    origin: str = ""  # «general (ALT14)» для семян, «мутация», «скрещивание», «случайная»
    born: int = 0

    def mean(self, tid: str) -> float:
        return sum(e.get(tid, 0) for e in self.evals) / len(self.evals) if self.evals else 0.0


@dataclass
class Score:
    fitness: float
    fixed: int
    broke: int


class Grader:
    """Потолок цели — лучший результат без запрета или у любого кандидата (как scan.grade)."""

    def __init__(self, baseline: dict[str, float]):
        self.baseline = baseline
        self.cap = dict(baseline)

    def see(self, c: Cand) -> None:
        for tid in self.cap:
            self.cap[tid] = max(self.cap[tid], c.mean(tid))

    def blocked(self) -> list[str]:
        return [t for t, cap in self.cap.items() if cap > 0 and self.baseline[t] < cap]

    def controls(self) -> list[str]:
        return [t for t, cap in self.cap.items() if cap > 0 and self.baseline[t] >= cap]

    def score(self, c: Cand) -> Score:
        if c.invalid or not c.evals:
            return Score(-1e9, 0, 0)
        part = {t: min(1.0, c.mean(t) / self.cap[t]) for t in self.cap if self.cap[t] > 0}
        b, ctl = self.blocked(), self.controls()
        fixed = sum(1 for t in b if part[t] >= 1 - 1e-9)
        broke = sum(1 for t in ctl if part[t] < 1 - 1e-9)
        ms = sum(c.ms) / len(c.ms) if c.ms else 0
        # сломать открытое так же плохо, как не починить закрытое; короче и быстрее — лучше при равенстве
        fit = sum(part[t] for t in b) - sum(1 - part[t] for t in ctl) - 0.02 * len(c.genome) - 0.00001 * ms
        return Score(round(fit, 5), fixed, broke)


Evaluate = Callable[[Genome], tuple[dict[str, float], int] | None]  # None — winws2 не запустился


# ---------- движок ----------

POP = 16
ELITE = 4
RETESTS = 3  # сколько раз перепроверить лучшего, прежде чем верить ему
NET_WAIT = 60


def evolve(job: Job, *, evaluate: Evaluate, baseline: dict[str, float], seeds: dict[str, Genome],
           deadline: float, names: dict[str, str] | None = None, state: dict | None = None,
           save: Callable[[dict], None] | None = None, net_ok: Callable[[], bool] | None = None,
           rng: random.Random | None = None, now: Callable[[], float] = time.time,
           sleep: Callable[[float], None] = time.sleep, max_evals: int | None = None,
           stop_when_ideal: bool = True, domains: list[str] | None = None) -> dict:
    """Крутится до deadline (или max_evals, или job.cancelled). Возвращает сводку для UI."""
    rng = rng or random.Random()
    names = names or {}
    grader = Grader(baseline)
    pool: dict[str, Cand] = {}
    gen, started, history = 0, now(), []
    if state:  # продолжаем прошлый запуск
        for k, d in state["pool"].items():
            c = Cand(tuple(parse_step(s) for s in d["steps"]), d["evals"], d["ms"], d["invalid"], d["origin"], d["born"])
            if None not in c.genome:
                pool[k] = c
        gen, history = state["generation"], state["history"]
        started = now() - state.get("elapsed", 0)
        job.say(f"Продолжаю: поколение {gen}, проверено {len(pool)} вариантов")
    for c in pool.values():
        grader.see(c)
    evals_done = 0
    t_begin = now()

    def out_of_time() -> bool:
        return job.cancelled or now() >= deadline or (max_evals is not None and evals_done >= max_evals)

    def run_one(c: Cand) -> None:
        nonlocal evals_done
        while True:
            r = evaluate(c.genome)
            evals_done += 1
            if r is None:
                c.invalid = True
                return
            res, ms = r
            # всё по нулям, хотя раньше что-то открывалось, — сначала убедимся, что интернет есть
            if net_ok and grader.controls() and not any(res.values()) and not net_ok():
                job.say("Похоже, пропал интернет — жду и проверю этот вариант заново", "warn")
                while not out_of_time() and not net_ok():
                    sleep(NET_WAIT)
                if out_of_time():
                    pool.pop(key(c.genome), None)  # не проверен — продолжение подберёт его заново
                    return
                job.say("Интернет вернулся, продолжаю")
                continue
            c.evals.append(res)
            c.ms.append(ms)
            grader.see(c)
            return

    def ranked() -> list[tuple[Score, str]]:
        sc = [(grader.score(c), k) for k, c in pool.items() if c.evals or c.invalid]
        # при равенстве выше тот, кого чаще перепроверяли: ему больше веры
        return sorted(sc, key=lambda x: (-x[0].fitness, -min(len(pool[x[1]].evals), RETESTS), x[1]))

    def summary(phase: str) -> dict:
        r = ranked()
        b = grader.blocked()
        top = []
        for s, k in r[:8]:
            c = pool[k]
            if c.invalid:
                continue
            steps = [str(x) for x in c.genome]
            top.append({"key": k, "steps": steps, "fitness": s.fitness, "fixed": s.fixed,
                        "code": share_code(steps, f"чинит {s.fixed} из {len(b)}, {time.strftime('%d.%m.%Y')}", domains),
                        "broke": s.broke, "evals": len(c.evals), "ms": round(sum(c.ms) / len(c.ms)) if c.ms else None,
                        "origin": c.origin, "born": c.born,
                        "targets": {t: round(c.mean(t), 2) for t in grader.cap}})
        return {"phase": phase, "generation": gen, "evaluated": len(pool), "started": started,
                "elapsed": round(now() - started),
                "deadline": deadline, "blocked": [names.get(t, t) for t in b],
                "controls": [names.get(t, t) for t in grader.controls()],
                "dead": [names.get(t, t) for t, cap in grader.cap.items() if cap == 0],
                "blocked_count": len(b), "best": top, "history": history[-300:]}

    def persist(phase: str) -> None:
        job.progress = 1.0 if phase == "done" else min(0.99, (now() - t_begin) / max(1.0, deadline - t_begin))
        job.result = summary(phase)
        if save:
            save({"pool": {k: {"steps": [str(s) for s in c.genome], "evals": c.evals, "ms": c.ms, "invalid": c.invalid,
                               "origin": c.origin, "born": c.born} for k, c in pool.items()},
                  "generation": gen, "history": history, "elapsed": now() - started, "baseline": baseline,
                  "summary": job.result})

    def ideal_confirmed() -> bool:
        r = ranked()
        if not r or not grader.blocked():
            return False
        s, k = r[0]
        return s.fixed == len(grader.blocked()) and s.broke == 0 and len(pool[k].evals) >= RETESTS

    # первое поколение: готовые стратегии + случайные
    if not pool:
        for name, g in seeds.items():
            pool.setdefault(key(g), Cand(g, origin=name))
        while len(pool) < POP:
            g = random_genome(rng)
            pool.setdefault(key(g), Cand(g, origin="случайная"))
        job.say(f"Первое поколение: {len(seeds)} из готовых стратегий, {len(pool) - len(seeds)} случайных")
        for i, c in enumerate(list(pool.values())):
            if out_of_time():
                break
            run_one(c)
            if i % 4 == 3:
                persist("first")
        persist("first")

    while not out_of_time():
        if stop_when_ideal and ideal_confirmed():
            job.say("Найдена стратегия, которая чинит всё и ничего не ломает, — перепроверена "
                    f"{RETESTS} раза. Останавливаюсь", "ok")
            break
        gen += 1
        r = [k for s, k in ranked() if not pool[k].invalid]
        if not r:
            break
        elite = r[:ELITE]
        parents = r[:POP]

        def pick() -> Genome:
            best = min(rng.sample(parents, min(3, len(parents))), key=parents.index)
            return pool[best].genome

        # лучшего, если он ещё мало проверен, — перепроверить: сеть шумит
        for k in elite[:2]:
            if len(pool[k].evals) < RETESTS and not out_of_time():
                run_one(pool[k])
        born = 0
        for _ in range(POP - ELITE):
            if out_of_time():
                break
            for _ in range(30):
                if rng.random() < 0.5 and len(parents) > 1:
                    g, origin = crossover(pick(), pick(), rng), "скрещивание"
                    if rng.random() < 0.5:
                        g = mutate(g, rng)
                else:
                    g, origin = mutate(pick(), rng), "мутация"
                if key(g) not in pool:
                    break
            else:
                g, origin = random_genome(rng), "случайная"
                if key(g) in pool:
                    continue
            c = Cand(g, origin=origin, born=gen)
            pool[key(g)] = c
            run_one(c)
            born += 1
        top = ranked()
        if top:
            s, k = top[0]
            history.append({"gen": gen, "t": round(now() - started), "fitness": s.fitness, "fixed": s.fixed,
                            "broke": s.broke})
            if gen % 5 == 0 or gen == 1:
                job.say(f"Поколение {gen}: лучшая чинит {s.fixed} из {len(grader.blocked())}, "
                        f"ломает {s.broke} — {k}")
        if born == 0 and not out_of_time():
            job.say("Новых вариантов не осталось", "warn")
            break
        persist("running")

    persist("done")
    return job.result


# ---------- настоящий запуск ----------

def _state_file() -> Path:
    from .settings import DATA_DIR
    return DATA_DIR / "evolve-state.json"


def load_state() -> dict | None:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_last() -> dict | None:
    st = load_state()
    return st.get("summary") if st else None


def probe_args(zdir: Path, g: Genome) -> list[str]:
    """Отдельный winws2 только для TLS на 443: на время проверки — ко всем сайтам, без списков."""
    lua = str(zdir).rstrip("\\/") + "\\lua\\"
    args = ["--chdir", "--wf-tcp-empty=0", "--wf-tcp-in=443", "--wf-tcp-out=443"]
    args += [f"--lua-init=@{lua}{f}" for f in ("zapret-lib.lua", "zapret-antidpi.lua", "blobs.lua")]
    args += ["--filter-tcp=443", "--payload=tls_client_hello"] + [f"--lua-desync={s}" for s in g]
    return args


# контрольные сайты, если среди выбранных целей нет ни одной открытой: по ним видно «сломала» и «нет сети»
CONTROLS = [("ctl-ya", "ya.ru"), ("ctl-vk", "vk.com")]


def run_evolve(job: Job, zdir: Path, targets: list[dict], hours: float, resume: bool = False) -> dict:
    if zapret.engine_of(zdir).id != "zapret2":
        raise EvolveError("эволюция работает с zapret2 — переключите движок на «Пульте»")
    if not zapret.winws_exe(zdir).exists():
        raise EvolveError(f"нет {zapret.winws_exe(zdir)}")
    if not scan.CURL.exists():
        raise EvolveError(f"нет {scan.CURL}")
    state = load_state() if resume else None
    if resume and not state:
        raise EvolveError("нечего продолжать — прошлого запуска нет")
    if state:
        targets = state.get("targets") or targets  # продолжаем на тех же целях, иначе оценки несравнимы
    targets = [t for t in targets if t["kind"] in ("url", "dpi")]  # игровые IP по TLS не проверить
    have = {t["id"] for t in targets}
    targets += [scan.target(i, h, "url", "Контроль", url="https://" + h, about="Контрольный сайт")
                for i, h in CONTROLS if i not in have]
    names = {t["id"]: t["name"] for t in targets}
    deadline = time.time() + hours * 3600

    payload = scan.make_payload()

    def evaluate(g: Genome):
        for attempt in range(2):  # сбой запуска бывает и случайным (драйвер не успел выгрузиться)
            try:
                proc = scan.launch(zdir, probe_args(zdir, g))
                break
            except (scan.ScanError, OSError):
                scan.stop_winws(None)
        else:
            return None  # дважды не запустился — winws2 не принимает эти аргументы
        try:
            res = scan.check_all(targets, payload)
        finally:
            scan.stop_winws(proc)
        return {t: r["score"] for t, r in res.items()}, sum(r["ms"] for r in res.values())

    control_targets = [t for t in targets if t["group"] == "Контроль"]

    def net_ok() -> bool:  # winws2 уже остановлен — проверяем голый интернет
        return any(r["score"] > 0 for r in scan.check_all(control_targets, payload).values())

    def save(st: dict) -> None:
        st["targets"] = targets
        write_text_atomic(_state_file(), json.dumps(st, ensure_ascii=False))

    try:
        with winutil.keep_awake(), suspend.suspended(zdir, job.say) as was:
            job.say(f"Служба: {was.service or 'не установлена'} — на время эволюции остановлена, потом вернётся")
            if state:
                baseline = state["baseline"]
            else:
                job.say("Прогон без запрета — что заблокировано")
                base = scan.check_all(targets, payload)
                baseline = {t: r["score"] for t, r in base.items()}
                if not any(baseline[t["id"]] > 0 for t in control_targets):
                    raise EvolveError("без запрета не открываются даже ya.ru и vk.com — похоже, нет интернета")
            blocked = [names[t] for t, s in baseline.items() if s < 1]
            if not blocked:
                raise EvolveError("без запрета все цели открываются — чинить нечего. Добавьте заблокированный сайт")
            job.say("Не открывается без запрета: " + ", ".join(blocked))
            seeds = {}
            if not state:
                seeds = seeds_from(zdir)
                imported = {f"импорт: {s['note'] or s['code'][:24]}": g for s in load_imports()
                            if (g := tuple(parse_step(x) for x in s["steps"])) and None not in g and valid(g)}
                if imported:
                    job.say(f"Чужие конфиги в стартовом поколении: {len(imported)}")
                seeds = imported | seeds  # чужие — первыми
            job.say(f"Ищу до {time.strftime('%H:%M', time.localtime(deadline))}. Компьютер не уснёт, пока идёт поиск")
            return evolve(job, evaluate=evaluate, baseline=baseline, seeds=seeds, deadline=deadline, names=names,
                          state=state, save=save, net_ok=net_ok, domains=custom_domains(targets))
    finally:
        payload.unlink(missing_ok=True)


# ---------- обмен найденным ----------
#
# Код — читаемая строка, чтобы перед вставкой было видно, что внутри:
#     pipo:v1:fake:blob=tls_google:tcp_md5|multisplit:pos=midsld#чинит 6 из 6, Ростелеком
# Внутри только шаги из нашего набора генов и безопасные для cmd символы — проверяет parse_code.

CODE_PREFIX = "pipo:v1:"
_SAFE_STEP = re.compile(r"[A-Za-z0-9_.:=,+-]+")


@dataclass
class Shared:
    steps: list[str]
    domains: list[str] = field(default_factory=list)  # «свои цели», ради которых искали: их — в сплит через запрет
    note: str = ""


def share_code(steps: list[str], note: str = "", domains: list[str] | None = None) -> str:
    note = re.sub(r"[\r\n#]+", " ", note).strip()[:80]
    dom = f";d={','.join(domains)}" if domains else ""
    return CODE_PREFIX + "|".join(steps) + dom + (f"#{note}" if note else "")


def check_steps(steps: list[str]) -> list[str]:
    """Только знакомые функции, допустимая цепочка и безопасные символы. Иначе — EvolveError."""
    if not steps:
        raise EvolveError("в коде нет ни одного шага")
    for s in steps:
        if parse_step(s) is None or not _SAFE_STEP.fullmatch(s):
            raise EvolveError(f"незнакомый или небезопасный шаг: {s[:60]}")
    if not valid(tuple(parse_step(s) for s in steps)):
        raise EvolveError("цепочка не годится: не больше двух фейков и один разрезатель в конце")
    return steps


def parse_code(text: str) -> Shared:
    """Код от друга → Shared. Понимает и голую цепочку «шаг → шаг»."""
    from . import split
    s = (text or "").strip()
    if s.lower().startswith(CODE_PREFIX):
        s = s[len(CODE_PREFIX):]
    s, _, note = s.partition("#")
    s, _, dom = s.partition(";d=")
    steps = [x.strip() for x in re.split(r"\s*(?:\||→|->|\n)\s*", s) if x.strip()]
    domains = []
    for d in filter(None, (x.strip() for x in dom.split(","))):
        try:
            kind, value = split.normalize(d)
        except split.SplitError:
            raise EvolveError(f"в коде странный домен: {d[:60]}") from None
        if kind != "domain":
            raise EvolveError(f"в коде не домен: {d[:60]}")
        domains.append(value)
    return Shared(check_steps(steps), list(dict.fromkeys(domains))[:20], note.strip()[:80])


def _imports_file() -> Path:
    from .settings import DATA_DIR
    return DATA_DIR / "evolve-imports.json"


def load_imports() -> list[dict]:
    try:
        data = json.loads(_imports_file().read_text(encoding="utf-8"))
        return [d for d in data if isinstance(d, dict) and isinstance(d.get("steps"), list)]
    except (OSError, ValueError):
        return []


def add_import(code: str) -> dict:
    sh = parse_code(code)
    items = [d for d in load_imports() if d["steps"] != sh.steps]
    item = {"steps": sh.steps, "note": sh.note, "code": share_code(sh.steps, sh.note, sh.domains), "added": time.time()}
    write_text_atomic(_imports_file(), json.dumps(items + [item], ensure_ascii=False))
    return item


def clear_imports() -> None:
    _imports_file().unlink(missing_ok=True)


def custom_domains(targets: list[dict]) -> list[str]:
    """Домены «своих целей»: стратегия из списков их не знает — при применении они идут в сплит через запрет."""
    from urllib.parse import urlsplit
    out = []
    for t in targets:
        host = urlsplit(t.get("url") or "").hostname
        if t.get("group") == "Свои" and host and host not in out:
            out.append(host)
    return out


# ---------- найденное — в .bat ----------

# По образцу general (SIMPLE FAKE) сборки kinlay0: QUIC, Discord и игры — как там,
# а для TLS (YouTube, домены из списков, IP из ipset) — найденная цепочка.
_TEMPLATE = r'''@echo off
chcp 65001 > nul
:: 65001 - UTF-8
:: Создано Пипо Алексеем (эволюция стратегий): {about}

cd /d "%~dp0"
call service.bat status_zapret
call service.bat load_game_filter
call service.bat load_user_lists
echo:

set "BIN=%~dp0bin\"
set "LISTS=..\lists\"
set "LUA=..\lua\"
cd /d "%BIN%"

start "zapret: %~n0" /min "%BIN%winws2.exe" --wf-tcp-empty=0 --ctrack-disable=0 ^
--wf-tcp-in=80,443,2053,2083,2087,2096,8443,%GameFilterTCP% --wf-udp-in=443,19294-19344,50000-50100,%GameFilterUDP% ^
--wf-tcp-out=80,443,2053,2083,2087,2096,8443,%GameFilterTCP% --wf-udp-out=443,19294-19344,50000-50100,%GameFilterUDP% ^
--lua-init=@"%LUA%zapret-lib.lua" ^
--lua-init=@"%LUA%zapret-antidpi.lua" ^
--lua-init=@"%LUA%zapret-auto.lua" ^
--lua-init=@"%LUA%blobs.lua" ^
--name="domain quic" --filter-udp=443 --hostlist="%LISTS%list-general.txt" --hostlist="%LISTS%list-general-user.txt" --hostlist-exclude="%LISTS%list-exclude.txt" --hostlist-exclude="%LISTS%list-exclude-user.txt" --ipset-exclude="%LISTS%ipset-exclude.txt" --ipset-exclude="%LISTS%ipset-exclude-user.txt" --payload=quic_initial --lua-desync=fake:blob=quic_google:repeats=6 --new ^
--name="discord voice" --filter-udp=19294-19344,50000-50100 --filter-l7=discord,stun --payload=discord_ip_discovery,stun --lua-desync=fake:blob=active_discord:repeats=6 --new ^
--name="discord media" --filter-tcp=2053,2083,2087,2096,8443 --hostlist-domains=discord.media --payload=tls_client_hello --lua-desync=fake:blob=tls_google:repeats=6:tcp_ts=-600000 --new ^
--name="youtube" --filter-tcp=443 --hostlist="%LISTS%list-google.txt" --payload=tls_client_hello {tls} --new ^
--name="domain tls" --filter-tcp=80,443 --hostlist="%LISTS%list-general.txt" --hostlist="%LISTS%list-general-user.txt" --hostlist-exclude="%LISTS%list-exclude.txt" --hostlist-exclude="%LISTS%list-exclude-user.txt" --ipset-exclude="%LISTS%ipset-exclude.txt" --ipset-exclude="%LISTS%ipset-exclude-user.txt" --payload=tls_client_hello {tls} --payload=http_req --lua-desync=fake:blob=tls_teamspeak:repeats=6:tcp_ts=-600000 --lua-desync=multisplit:pos=2 --new ^
--name="ip quic" --filter-udp=443 --ipset="%LISTS%ipset-all.txt" --hostlist-exclude="%LISTS%list-exclude.txt" --hostlist-exclude="%LISTS%list-exclude-user.txt" --ipset-exclude="%LISTS%ipset-exclude.txt" --ipset-exclude="%LISTS%ipset-exclude-user.txt" --payload=quic_initial --lua-desync=fake:blob=quic_google:repeats=6 --new ^
--name="ip tls" --filter-tcp=80,443,8443 --ipset="%LISTS%ipset-all.txt" --hostlist-exclude="%LISTS%list-exclude.txt" --hostlist-exclude="%LISTS%list-exclude-user.txt" --ipset-exclude="%LISTS%ipset-exclude.txt" --ipset-exclude="%LISTS%ipset-exclude-user.txt" --payload=tls_client_hello {tls} --payload=http_req --lua-desync=fake:blob=tls_teamspeak:repeats=6:tcp_ts=-600000 --lua-desync=multisplit:pos=2 --new ^
--name="gamefiltertcp" --filter-tcp=%GameFilterTCP% --ipset="%LISTS%ipset-all.txt" --ipset-exclude="%LISTS%ipset-exclude.txt" --ipset-exclude="%LISTS%ipset-exclude-user.txt" --out-range=-n4 --payload=tls_client_hello,unknown --lua-desync=fake:blob=tls_google:repeats=6:tcp_ts=-600000:payload=tls_client_hello,unknown --new ^
--name="gamefilterudp" --filter-udp=%GameFilterUDP% --ipset="%LISTS%ipset-all.txt" --ipset-exclude="%LISTS%ipset-exclude.txt" --ipset-exclude="%LISTS%ipset-exclude-user.txt" --out-range=-n3 --payload=all --lua-desync=fake:blob=active_game:repeats=12:payload=all
'''


def render_bat(steps: list[str], about: str = "") -> str:
    tls = " ".join(f"--lua-desync={s}" for s in steps)
    return _TEMPLATE.replace("{tls}", tls).replace("{about}", about or " → ".join(steps))


_EVO_NAME = re.compile(r"^general \(PIPO EVO (\d+)\)$")


def save_bat(zdir: Path, steps: list[str]) -> str:
    """Записать найденную цепочку стратегией general (PIPO EVO N). Та же цепочка второй раз не пишется."""
    text = render_bat(steps)
    nums = []
    for name in zapret.list_strategies(zdir):
        m = _EVO_NAME.match(name)
        if m:
            nums.append(int(m.group(1)))
            try:
                if (zdir / f"{name}.bat").read_text(encoding="utf-8") == text:
                    return name
            except OSError:
                pass
    check_steps(steps)  # только знакомые функции и безопасные для cmd символы: без кавычек, %, ^, & и пробелов
    name = f"general (PIPO EVO {max(nums, default=0) + 1})"
    # CRLF, как у .bat сборки: cmd с одними LF ненадёжен. Через временный файл — без полуфайлов
    path = zdir / f"{name}.bat"
    tmp = path.with_name(path.name + ".pipo-tmp")
    tmp.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    os.replace(tmp, path)
    return name
