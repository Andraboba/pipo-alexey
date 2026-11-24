"""HTTP API + раздача UI. Слушаем только 127.0.0.1.

Сервер работает с правами администратора, поэтому любой сайт в браузере не
должен иметь возможности дёрнуть API:
  * Host обязан быть 127.0.0.1/localhost (защита от DNS rebinding);
  * каждый запрос к /api несёт X-Pipo-Token — случайный токен этого запуска,
    который есть только в отданной нами странице. Кастомный заголовок к тому же
    вызывает CORS preflight, а CORS мы не разрешаем.
"""
from __future__ import annotations

import os
import secrets
import socket
import ssl
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import (__version__, dnscheck, evolve, hostsmod, jobs, presets, scan, settings, split, switch, tgproxy, updater,
               winutil, zapret)

# PIPO_TOKEN — только для разработки фронта (vite dev); в обычном запуске токен случайный
TOKEN = os.environ.get("PIPO_TOKEN") or secrets.token_urlsafe(24)
DIST_DIR = settings.WEB_DIR / "dist"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
# окно-оболочка закрывается: main.py остановит задачу (она вернёт запрет как было) и выключит сервер
QUIT = threading.Event()

app = FastAPI(title="pipo", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def guard(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "forbidden host"}, status_code=403)
    if request.url.path.startswith("/api/") and not secrets.compare_digest(
        request.headers.get("x-pipo-token", ""), TOKEN
    ):
        return JSONResponse({"detail": "bad token — обновите страницу"}, status_code=403)
    busy = _busy_with(request)
    if busy:
        return JSONResponse({"detail": f"Сейчас идёт {busy} — дождитесь окончания или остановите"}, status_code=409)
    resp: Response = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


JOB_NAMES = {
    "scan": "подбор стратегии", "evolve": "эволюция стратегий", "zapret": "обновление zapret", "zapret2": "обновление zapret2", "tg": "обновление TG WS Proxy",
    "ipset": "обновление IPSet", "asn": "обновление подсетей по ASN", "recover": "возврат запрета после прошлого запуска",
}


def _busy_with(request: Request) -> str | None:
    """Пока задача держит запрет на паузе, любые изменения ломают её результат или её возврат «как было».

    Читать можно, остановить задачу можно; всё остальное — 409. Одно правило вместо проверки в каждом обработчике."""
    path = request.url.path
    if (request.method in ("GET", "HEAD") or not path.startswith("/api/") or path.startswith("/api/jobs/")
            or path in ("/api/app/quit", "/api/ui")):
        return None
    job = jobs.current()
    return JOB_NAMES.get(job.kind, "другая операция") if job else None


def zdir() -> Path:
    return settings.zapret_dir()


def need_admin() -> None:
    if not winutil.is_admin():
        raise HTTPException(403, "нужны права администратора — запустите Пипо Алексея заново и разрешите запрос")


def fail(e: Exception, code: int = 400):
    raise HTTPException(code, str(e)) from e


ERRORS = (zapret.ServiceError, zapret.StrategyError, split.SplitError, updater.UpdateError, jobs.Busy, scan.ScanError,
          switch.SwitchError, evolve.EvolveError, OSError)


# ---------- страница ----------

@app.get("/", response_class=HTMLResponse)
def index():
    try:
        html = (DIST_DIR / "index.html").read_text(encoding="utf-8")
    except OSError:
        return HTMLResponse("UI не собран: выполните <code>npm install && npm run build</code> в папке frontend", 503)
    return html.replace("__PIPO_TOKEN__", TOKEN)


@app.post("/api/app/quit")
def app_quit():
    """Выход из трея: ответ сразу, сама остановка — в main.py."""
    QUIT.set()
    return {"ok": True}


DIST_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=DIST_DIR), name="static")


# ---------- статус ----------

@app.get("/api/status")
def status():
    z = zdir()
    return {
        "version": __version__,
        "admin": winutil.is_admin(),
        "zapret": zapret.status(z),
        "tg": tgproxy.status(),
        "job": (j.to_dict() if (j := jobs.current()) else None),
    }


# ---------- служба запрета ----------

@app.post("/api/zapret/install")
def zapret_install(strategy: str = Body(..., embed=True), start: bool = Body(False, embed=True)):
    need_admin()
    try:
        zapret.install_service(zdir(), strategy, start=start)
        switch.remember_strategy(settings.engine(), strategy)
    except ERRORS as e:
        fail(e)
    return zapret.status(zdir())


@app.put("/api/zapret/engine")
def zapret_engine(engine: str = Body(..., embed=True)):
    """Flowseal ⇄ zapret2. Работает только один: служба одна, драйвер WinDivert один."""
    need_admin()
    log: list[dict] = []
    try:
        res = switch.switch(engine, lambda text, level="info": log.append({"text": text, "level": level}))
    except ERRORS as e:
        fail(e)
    return res | {"log": log, "status": zapret.status(zdir())}


@app.post("/api/zapret/{action}")
def zapret_action(action: str):
    need_admin()
    fn = {"start": zapret.start_service, "stop": zapret.stop_all, "restart": zapret.restart_service,
          "remove": zapret.remove_service}.get(action)
    if not fn:
        raise HTTPException(404)
    try:
        fn()
    except ERRORS as e:
        fail(e)
    return zapret.status(zdir())


@app.put("/api/zapret/autostart")
def zapret_autostart(enabled: bool = Body(..., embed=True)):
    need_admin()
    try:
        zapret.set_autostart(enabled)
    except ERRORS as e:
        fail(e)
    return zapret.status(zdir())


@app.put("/api/zapret/game-filter")
def game_filter(mode: str = Body(..., embed=True), tcp: str = Body(zapret.DEFAULT_GAME_RANGE, embed=True),
                udp: str = Body(zapret.DEFAULT_GAME_RANGE, embed=True)):
    need_admin()
    if mode not in ("disabled", "all", "tcp", "udp"):
        raise HTTPException(400, "режим: disabled, all, tcp, udp")
    vt, vu = zapret.validate_range(tcp), zapret.validate_range(udp)
    if not vt or not vu:
        raise HTTPException(400, "порты: например 1024-65535 или 1024-1934,1936-65535")
    try:
        zapret.write_game_filter(zdir(), zapret.GameFilter(mode, vt, vu))
        restart = zapret.reconfigure_service(zdir())
    except ERRORS as e:
        fail(e)
    return {"status": zapret.status(zdir()), "restart_needed": restart}


@app.put("/api/zapret/ipset-mode")
def ipset_mode(mode: str = Body(..., embed=True)):
    need_admin()
    try:
        split.set_ipset_mode(zdir(), mode)
    except ERRORS as e:
        fail(e)
    return {"status": zapret.status(zdir()), "restart_needed": zapret.service_state() == "running"}


# ---------- сплит ----------

def _split_resp():
    return split.snapshot(zdir()) | {"restart_needed": zapret.service_state() == "running"}


@app.get("/api/split")
def split_get():
    return split.snapshot(zdir())


@app.post("/api/split/rules")
def rule_add(value: str = Body(..., embed=True), route: str = Body(..., embed=True), note: str = Body("", embed=True),
             kind: str | None = Body(None, embed=True)):
    need_admin()
    try:
        split.add_rule(zdir(), value, route, note, kind=kind)
    except ERRORS as e:
        fail(e)
    return _split_resp()


@app.patch("/api/split/rules/{rule_id}")
def rule_patch(rule_id: str, patch: dict = Body(...)):
    need_admin()
    try:
        split.update_rule(zdir(), rule_id, patch)
    except ERRORS as e:
        fail(e)
    return _split_resp()


@app.delete("/api/split/rules/{rule_id}")
def rule_delete(rule_id: str):
    need_admin()
    try:
        split.delete_rule(zdir(), rule_id)
    except ERRORS as e:
        fail(e)
    return _split_resp()


@app.post("/api/split/profiles")
def profile_add(name: str = Body("", embed=True), networks: str = Body("", embed=True), route: str | None = Body(None, embed=True),
                domains: str = Body("", embed=True), asns: str = Body("", embed=True), preset: str | None = Body(None, embed=True)):
    need_admin()
    try:
        if preset:
            pr = presets.get(preset)
            if not pr:
                raise split.SplitError("нет такого пресета")
            split.add_profile(zdir(), pr["name"], "\n".join(pr.get("networks", [])), route or pr["default_route"],
                              domains=pr["domains"], asns=[a["asn"] for a in pr["asns"]], preset=preset)
        else:
            split.add_profile(zdir(), name, networks, route or "zapret", domains=domains, asns=asns)
    except ERRORS as e:
        fail(e)
    return _split_resp()


@app.get("/api/presets")
def presets_list():
    added = {p["preset"] for p in split.snapshot(zdir())["profiles"] if p.get("preset")}
    return [p | {"added": p["id"] in added} for p in presets.PRESETS]


@app.post("/api/split/profiles/refresh")
def profiles_refresh():
    need_admin()
    z = zdir()
    try:
        job = jobs.start("asn", lambda j: {"prefixes": split.refresh_profile_asns(z, log=j.say)})
    except jobs.Busy as e:
        fail(e, 409)
    return job.to_dict()


@app.patch("/api/split/profiles/{profile_id}")
def profile_patch(profile_id: str, patch: dict = Body(...)):
    need_admin()
    try:
        split.update_profile(zdir(), profile_id, patch)
    except ERRORS as e:
        fail(e)
    return _split_resp()


@app.delete("/api/split/profiles/{profile_id}")
def profile_delete(profile_id: str):
    need_admin()
    try:
        split.delete_profile(zdir(), profile_id)
    except ERRORS as e:
        fail(e)
    return _split_resp()


@app.get("/api/check-host")
def check_host(host: str):
    """Открывается ли сайт прямо сейчас: DNS → TCP:443 → TLS → HTTP HEAD."""
    try:
        kind, value = split.normalize(host)
    except split.SplitError as e:
        fail(e)
    steps = []
    t0 = time.perf_counter()
    try:
        infos = socket.getaddrinfo(value, 443, type=socket.SOCK_STREAM)
        ip = infos[0][4][0]
        steps.append({"step": "dns", "ok": True, "detail": ip})
        with socket.create_connection((ip, 443), timeout=5) as raw:
            steps.append({"step": "tcp", "ok": True, "detail": f"{(time.perf_counter() - t0) * 1000:.0f} мс"})
            ctx = ssl.create_default_context()
            sni = value if kind == "domain" else None
            if not sni:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with ctx.wrap_socket(raw, server_hostname=sni) as tls:
                tls.settimeout(6)
                steps.append({"step": "tls", "ok": True, "detail": tls.version()})
                tls.sendall(f"HEAD / HTTP/1.1\r\nHost: {value}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n".encode())
                first = tls.recv(256).split(b"\r\n", 1)[0].decode("latin-1", "replace")
                steps.append({"step": "http", "ok": bool(first), "detail": first or "пустой ответ"})
    except socket.gaierror as e:
        steps.append({"step": "dns", "ok": False, "detail": str(e)})
    except (OSError, ssl.SSLError) as e:
        names = ["dns", "tcp", "tls", "http"]
        steps.append({"step": names[min(len(steps), 3)], "ok": False, "detail": type(e).__name__ + ": " + str(e)[:160]})
    ok = bool(steps) and all(s["ok"] for s in steps) and len(steps) == 4
    return {"host": value, "ok": ok, "ms": round((time.perf_counter() - t0) * 1000), "steps": steps,
            "zapret_running": zapret.service_state() == "running" or zapret.winws_running()}


# ---------- TG WS Proxy ----------

def _tg_exe() -> Path:
    exe = tgproxy.find_exe()
    if not exe:
        raise HTTPException(404, "TG WS Proxy не найден — установите его во вкладке «Обновления»")
    return exe


@app.post("/api/tg/{action}")
def tg_action(action: str):
    exe = _tg_exe()
    try:
        if action == "start":
            tgproxy.start(exe)
            for _ in range(16):
                if tgproxy.running(exe):
                    break
                time.sleep(0.25)
        elif action == "stop":
            tgproxy.stop(exe)
        elif action == "open-link":
            link = tgproxy.status()["link"]
            if not link:
                raise HTTPException(400, "в конфиге TG WS Proxy нет secret — запустите прокси хотя бы раз")
            winutil.open_url_unelevated(link)
        else:
            raise HTTPException(404)
    except ERRORS as e:  # Popen/реестр: файл занят, нет прав
        fail(e)
    return tgproxy.status()


@app.put("/api/tg/autostart")
def tg_autostart(enabled: bool = Body(..., embed=True)):
    try:
        tgproxy.set_autostart(_tg_exe(), enabled)
    except ERRORS as e:
        fail(e)
    return tgproxy.status()


# ---------- обновления ----------

@app.get("/api/updates")
def updates(force: bool = False):
    return updater.check(force=force)


@app.post("/api/updates/{target}")
def update_run(target: str, confirm: bool = Body(False, embed=True), version: str | None = Body(None, embed=True)):
    need_admin()
    if not confirm:
        raise HTTPException(400, "обновление ставится только после подтверждения")
    z = zdir()
    try:
        if target in ("zapret", "zapret2"):
            engine = "flowseal" if target == "zapret" else "zapret2"
            ez = settings.engine_dir(engine)
            job = jobs.start(target, lambda j: updater.update_zapret(j, ez, version, engine))
        elif target == "tg":
            job = jobs.start("tg", lambda j: updater.update_tg(j, version))
        elif target == "ipset":
            job = jobs.start("ipset", lambda j: updater.update_ipset(j, z))
        else:
            raise HTTPException(404)
    except jobs.Busy as e:
        fail(e, 409)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def job_get(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    job.cancelled = True
    return job.to_dict()


# ---------- доступ к сервисам через hosts (без Claude/Anthropic) ----------

@app.get("/api/hosts")
def hosts_get():
    return hostsmod.overview()


@app.post("/api/hosts/refresh")
def hosts_refresh():
    errors = []
    for key in hostsmod.SOURCES:
        try:
            hostsmod.fetch(key)
        except Exception as e:  # noqa: BLE001 — один источник недоступен, второй всё равно обновим
            errors.append(f"{hostsmod.SOURCES[key]['name']}: {e}")
    return hostsmod.overview() | {"errors": errors}


@app.put("/api/hosts")
def hosts_apply(source: str = Body(..., embed=True), sections: list[str] = Body(..., embed=True)):
    need_admin()
    try:
        hostsmod.apply(source, sections)
    except (hostsmod.HostsError, OSError) as e:
        fail(e)
    return hostsmod.overview()


@app.delete("/api/hosts")
def hosts_remove():
    need_admin()
    try:
        hostsmod.remove()
    except (hostsmod.HostsError, OSError) as e:
        fail(e)
    return hostsmod.overview()


@app.get("/api/hosts/check")
def hosts_check(domain: str):
    try:
        kind, value = split.normalize(domain)
        return hostsmod.check(value)
    except (split.SplitError, hostsmod.HostsError) as e:
        fail(e)


# ---------- подбор стратегии ----------

@app.get("/api/scan/targets")
def scan_targets():
    z = zdir()
    return {"targets": scan.available_targets(z), "strategies": zapret.list_strategies(z),
            "current": zapret.installed_strategy(), "last": scan.load_last(zapret.engine_of(z).id)}


@app.post("/api/scan")
def scan_run(strategies: list[str] = Body([], embed=True), target_ids: list[str] = Body([], embed=True),
             custom: str = Body("", embed=True), dpi: bool = Body(False, embed=True)):
    need_admin()
    z = zdir()
    targets = _scan_targets(z, target_ids, custom, dpi)
    if not targets:
        raise HTTPException(400, "выберите хотя бы одну цель")
    try:
        job = jobs.start("scan", lambda j: scan.run_scan(j, z, strategies, targets))
    except jobs.Busy as e:
        fail(e, 409)
    return job.to_dict()


# ---------- эволюция стратегий (zapret2) ----------

def _scan_targets(z: Path, target_ids: list[str], custom: str, dpi: bool) -> list[dict]:
    known = {t["id"]: t for t in scan.available_targets(z)}
    targets = [known[i] for i in target_ids if i in known] + scan.parse_custom(custom)
    if dpi:
        try:
            targets += scan.dpi_suite()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"не удалось скачать набор 16–20 КБ: {e}") from e
    return targets


@app.get("/api/evolve")
def evolve_get():
    z = zdir()
    st = evolve.load_state()
    return {"engine": zapret.engine_of(z).id, "targets": scan.available_targets(z), "last": evolve.load_last(),
            "can_resume": bool(st and st.get("targets")), "current": zapret.installed_strategy(),
            "imports": evolve.load_imports()}


@app.post("/api/evolve/import")
def evolve_import(code: str = Body(..., embed=True), save: bool = Body(False, embed=True)):
    """Код от друга: save=False — в стартовое поколение эволюции, save=True — сразу стратегией в папку zapret2."""
    need_admin()
    z = zdir()
    try:
        if not save:
            return {"imported": evolve.add_import(code), "imports": evolve.load_imports()}
        if zapret.engine_of(z).id != "zapret2":
            raise HTTPException(409, "код — стратегия zapret2, а сейчас включён другой движок")
        sh = evolve.parse_code(code)
        name = evolve.save_bat(z, sh.steps)
        return {"strategy": name, "added": _route_through_zapret(z, sh.domains), "status": zapret.status(z)}
    except ERRORS as e:
        fail(e)


@app.delete("/api/evolve/imports")
def evolve_imports_clear():
    need_admin()
    evolve.clear_imports()
    return {"imports": []}


@app.post("/api/evolve")
def evolve_run(target_ids: list[str] = Body([], embed=True), custom: str = Body("", embed=True),
               dpi: bool = Body(False, embed=True), hours: float = Body(6, embed=True), resume: bool = Body(False, embed=True)):
    need_admin()
    if not 0.05 <= hours <= 12:
        raise HTTPException(400, "время поиска: от 3 минут до 12 часов")
    z = zdir()
    targets = [] if resume else _scan_targets(z, target_ids, custom, dpi)
    if not resume and not targets:
        raise HTTPException(400, "выберите хотя бы одну цель")
    try:
        job = jobs.start("evolve", lambda j: evolve.run_evolve(j, z, targets, hours, resume=resume))
    except jobs.Busy as e:
        fail(e, 409)
    return job.to_dict()


@app.post("/api/evolve/save")
def evolve_save(key: str = Body(..., embed=True)):
    """Найденную цепочку — в general (PIPO EVO N).bat; применяет её потом обычная установка службы.

    Свои цели эволюции проверялись без списков, а в .bat цепочка работает только для доменов из списков —
    поэтому их домены добавляются в сплит «через запрет» (если пользователь не решил о них иначе)."""
    need_admin()
    z = zdir()
    if zapret.engine_of(z).id != "zapret2":
        raise HTTPException(409, "найденные стратегии — для zapret2, а сейчас включён другой движок")
    st = evolve.load_state()
    found = (st or {}).get("pool", {}).get(key)
    if not found:
        raise HTTPException(404, "такой стратегии нет в результатах — запустите эволюцию заново")
    try:
        name = evolve.save_bat(z, found["steps"])
        added = _route_through_zapret(z, evolve.custom_domains(st.get("targets", [])))
    except ERRORS as e:
        fail(e)
    return {"strategy": name, "added": added, "status": zapret.status(z)}


def _route_through_zapret(z: Path, domains: list[str]) -> list[str]:
    """Домены — в сплит «через запрет», если пользователь ещё не решил о них сам."""
    have = {r["value"] for r in split.snapshot(z)["rules"]}
    added = [d for d in domains if d not in have]
    for d in added:
        split.add_rule(z, d, "zapret", note="эволюция")
    return added


# ---------- диагностика ----------

@app.get("/api/diag/dns")
def dns_last():
    return dnscheck.load_last()


@app.post("/api/diag/dns")
def dns_run(domains: str = Body("", embed=True)):
    """Несколько секунд: сотни DNS-запросов параллельно. Ничего в системе не меняет."""
    extra = []
    for raw in domains.replace(",", " ").split():
        if raw.strip():
            try:
                kind, value = split.normalize(raw)
            except split.SplitError as e:
                fail(e)
            if kind != "domain":
                raise HTTPException(400, f"{raw.strip()}: нужен домен, а не IP")
            extra.append(value)
    report = dnscheck.run(extra[:10])
    dnscheck.save_last(report)
    return report


# ---------- настройки ----------

@app.get("/api/settings")
def settings_get():
    return settings.load()


UI_PREFS = {
    "theme": ("ui_theme", ("system", "dark", "light")),
    "scale": ("ui_scale", ("0.9", "1", "1.1", "1.25", "1.4")),
    "tour_done": ("ui_tour_done", (True, False)),
}


@app.put("/api/ui")
def ui_put(patch: dict = Body(...)):
    """Оформление интерфейса (тема, масштаб, пройденный гайд). Запрет не трогает — разрешено и во время подбора."""
    save = {}
    for k, v in patch.items():
        if k not in UI_PREFS:
            raise HTTPException(400, f"неизвестная настройка: {k}")
        key, allowed = UI_PREFS[k]
        if not any(v == a and type(v) is type(a) for a in allowed):
            raise HTTPException(400, f"{k}: одно из {', '.join(map(str, allowed))}")
        save[key] = v
    data = settings.save(save)
    return {k: data[key] for k, (key, _) in UI_PREFS.items()}


@app.put("/api/settings")
def settings_put(patch: dict = Body(...)):
    # движок меняется только через /api/zapret/engine: там служба и списки переносятся как надо
    patch = {k: v for k, v in patch.items() if k not in ("engine", "strategies") and not k.startswith("ui_")}
    if "zapret2_dir" in patch and not (isinstance(patch["zapret2_dir"], str) and patch["zapret2_dir"].strip()):
        raise HTTPException(400, "укажите папку zapret2")
    if "zapret2_dir" in patch and settings.engine() == "zapret2" and not (Path(patch["zapret2_dir"]) / "bin" / "winws2.exe").is_file():
        raise HTTPException(400, "zapret2 сейчас включён, а в этой папке нет bin\\winws2.exe")
    if "zapret_dir" in patch and not (isinstance(patch["zapret_dir"], str) and patch["zapret_dir"].strip()):
        raise HTTPException(400, "укажите папку запрета")
    if "tg_exe" in patch and patch["tg_exe"] is not None and not isinstance(patch["tg_exe"], str):
        raise HTTPException(400, "tg_exe: нужен путь строкой")
    if "zapret_dir" in patch and not (Path(patch["zapret_dir"]) / "service.bat").is_file():
        raise HTTPException(400, "в этой папке нет service.bat")
    if patch.get("tg_exe") and not Path(patch["tg_exe"]).is_file():
        raise HTTPException(400, "файл TG WS Proxy не найден")
    dirs = {k: patch.get(k) or settings.load()[k] for k in ("zapret_dir", "zapret2_dir")}
    if Path(dirs["zapret_dir"]).resolve() == Path(dirs["zapret2_dir"]).resolve():
        raise HTTPException(400, "у Flowseal и zapret2 должны быть разные папки")
    return settings.save(patch)
