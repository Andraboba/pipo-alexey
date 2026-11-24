"""Тесты на копиях во временной папке — C:\\Zapret не трогаем.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from app import split, suspend, updater, winutil, zapret
from app import settings as app_settings

BAT = r'''@echo off
cd /d "%~dp0"
set "BIN=%~dp0bin\"
set "LISTS=%~dp0lists\"
start "zapret: %~n0" /min "%BIN%winws.exe" --wf-tcp=80,443,%GameFilterTCP% --wf-udp=443,%GameFilterUDP% ^
--filter-tcp=443 --hostlist="%LISTS%list-general.txt" --dpi-desync=fake --dpi-desync-fake-tls="%BIN%tls.bin" --new ^
--filter-udp=%GameFilterUDP% --ipset="%LISTS%ipset-all.txt" --dpi-desync-fake-tls=^! --dpi-desync-cutoff=n2
'''


def make_zapret(root: Path) -> Path:
    z = root / "Zapret"
    (z / "bin").mkdir(parents=True)
    (z / "lists").mkdir()
    (z / "utils").mkdir()
    (z / "bin" / "winws.exe").write_bytes(b"old-winws")
    (z / "service.bat").write_text('@echo off\nset "LOCAL_VERSION=1.10.4"\n', encoding="utf-8")
    (z / "general.bat").write_text(BAT, encoding="utf-8")
    (z / "general (ALT).bat").write_text(BAT, encoding="utf-8")
    L = z / "lists"
    base = [f"10.{i}.0.0/16" for i in range(1, 200)]
    iracing = ["3.2.66.0/23", "10.5.0.0/16"]  # одна подсеть уже есть в базе
    (L / "ipset-all.txt.pre-iracing").write_text("\n".join(base) + "\n", encoding="utf-8")
    merged = base + ["3.2.66.0/23"]
    (L / "ipset-all.txt").write_text("\n".join(merged) + "\n", encoding="utf-8")
    (L / "ipset-all.txt.backup").write_text("\n".join(merged) + "\n", encoding="utf-8")
    (L / "ipset-iracing.txt").write_text("\n".join(iracing) + "\n", encoding="utf-8")
    (L / "ipset-exclude-user.txt").write_text(zapret.PLACEHOLDER_IP + "\n", encoding="utf-8")
    (L / "list-general-user.txt").write_text("# Never leave this file empty\ndomain.example.abc\nmy-blocked.org\n", encoding="utf-8")
    (L / "list-exclude-user.txt").write_text("domain.example.abc\n", encoding="utf-8")
    (L / "ipset-exclude.txt").write_text("10.0.0.0/8\n", encoding="utf-8")
    (z / "utils" / "game_filter.enabled").write_text("all\n", encoding="utf-8")
    return z


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pipo-test-"))
        self.z = make_zapret(self.tmp)
        self.data = self.tmp / "data"
        self.patches = [mock.patch.object(m, "DATA_DIR", self.data) for m in (split, suspend, updater, app_settings)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lines(self, name):
        return split.read_list(self.z / "lists" / name)


class StrategyTests(TempCase):
    def test_strategy_outside_zapret_dir_refused(self):
        (self.tmp / "evil.bat").write_text(BAT, encoding="utf-8")  # рядом с папкой запрета, но не в ней
        with self.assertRaises(zapret.StrategyError):
            zapret.build_args(self.z, "../evil", zapret.GameFilter("all", "1024-65535", "1024-65535"))

    def test_args_substitution(self):
        gf = zapret.GameFilter("udp", "1024-65535", "50000-60000")
        args = zapret.build_args(self.z, "general", gf)
        joined = " ".join(args)
        self.assertIn("--wf-tcp=80,443,12", joined)  # TCP выключен -> заглушка 12
        self.assertIn("--wf-udp=443,50000-60000", joined)
        self.assertIn(f"--hostlist={self.z}\\lists\\list-general.txt", args)
        self.assertIn("--dpi-desync-fake-tls=!", args)  # ^! -> !
        self.assertNotIn("^", joined)
        self.assertNotIn("%", joined)

    def test_path_with_spaces_keeps_quotes(self):
        z2 = self.tmp / "My Zapret"
        shutil.copytree(self.z, z2)
        args = zapret.build_args(z2, "general", zapret.GameFilter())
        self.assertIn(f'--hostlist="{z2}\\lists\\list-general.txt"', args)

    def test_unknown_variable(self):
        (self.z / "bad.bat").write_text('start "x" "%BIN%winws.exe" --x=%FOO%\n', encoding="utf-8")
        with self.assertRaises(zapret.StrategyError):
            zapret.build_args(self.z, "bad", zapret.GameFilter())

    def test_strategy_order_like_service_bat(self):
        self.assertEqual(zapret.list_strategies(self.z), ["general", "general (ALT)"])

    def test_game_filter_roundtrip_and_legacy(self):
        self.assertEqual(zapret.read_game_filter(self.z).mode, "all")  # старый формат «all»
        zapret.write_game_filter(self.z, zapret.GameFilter("tcp", "1024-2000", "3000"))
        gf = zapret.read_game_filter(self.z)
        self.assertEqual((gf.mode, gf.tcp, gf.udp), ("tcp", "1024-2000", "3000"))

    def test_range_validation(self):
        self.assertEqual(zapret.validate_range("1024-1934, 1936-65535"), "1024-1934,1936-65535")
        for bad in ("", "0-5", "70000", "500-100", "abc", "1024-"):
            self.assertIsNone(zapret.validate_range(bad), bad)


class NormalizeTests(unittest.TestCase):
    def test_cases(self):
        cases = {
            "https://Www.Example.com/path?q=1": ("domain", "www.example.com"),
            "*.discord.gg": ("domain", "discord.gg"),
            "site.ru:8443": ("domain", "site.ru"),
            "пример.рф": ("domain", "xn--e1afmkfd.xn--p1ai"),
            "1.2.3.4": ("ip", "1.2.3.4"),
            "1.2.3.4/24": ("ip", "1.2.3.0/24"),
            "2a05:d014::1/32": ("ip", "2a05:d014::/32"),
        }
        for raw, want in cases.items():
            self.assertEqual(split.normalize(raw), want, raw)
        for bad in ("", "localhost", "not a domain", "http://"):
            with self.assertRaises(split.SplitError, msg=bad):
                split.normalize(bad)


class SplitTests(TempCase):
    def test_bootstrap_detects_iracing_and_clean_base(self):
        snap = split.snapshot(self.z)
        prof = snap["profiles"][0]
        self.assertEqual((prof["name"], prof["route"]), ("iRacing", "zapret"))
        # база взята из .pre-iracing, т.к. pre ∪ iracing == текущий ipset-all
        self.assertNotIn("3.2.66.0/23", split.read_list(split.base_file()))
        self.assertEqual([r["value"] for r in snap["rules"]], ["my-blocked.org"])

    def test_corrupt_state_is_kept_aside(self):
        split.add_rule(self.z, "keep-me.org", "zapret")
        sf = split._state_file()
        sf.write_text(sf.read_text(encoding="utf-8")[:-20], encoding="utf-8")  # обрезанный JSON
        broken = sf.read_bytes()
        split.load(self.z)
        aside = list(sf.parent.glob(sf.name + ".corrupt-*"))
        self.assertEqual(len(aside), 1)
        self.assertEqual(aside[0].read_bytes(), broken)  # правила можно достать руками

    def test_unreadable_state_is_not_overwritten(self):
        split.add_rule(self.z, "keep-me.org", "zapret")
        sf = split._state_file()
        before = sf.read_bytes()
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("занят антивирусом")):
            with self.assertRaises(OSError):
                split.load(self.z)
        self.assertEqual(sf.read_bytes(), before)

    def test_unknown_fields_in_state_ignored(self):
        split.add_rule(self.z, "keep-me.org", "zapret")
        sf = split._state_file()
        raw = json.loads(sf.read_text(encoding="utf-8"))
        raw["future"] = 1
        raw["rules"][-1]["future_field"] = True
        sf.write_text(json.dumps(raw), encoding="utf-8")
        self.assertIn("keep-me.org", [r.value for r in split.load(self.z).rules])

    def test_coverage_counts_supernets(self):
        pool = ["10.0.0.0/8", "192.168.1.0/24", "2a05::/16"]
        self.assertEqual(split.coverage(["10.5.0.0/16", "10.255.255.0/24", "192.168.0.0/16", "2a05:d014::/32", "11.0.0.0/24"], pool), 3)

    def test_subtract_by_ranges(self):
        self.assertEqual(split.subtract(["10.0.0.0/24"], ["10.0.0.0/25"]), ["10.0.0.128/25"])
        self.assertEqual(split.subtract(["10.0.0.0/24"], ["10.0.0.64/26"]), ["10.0.0.0/26", "10.0.0.128/25"])
        self.assertEqual(split.subtract(["10.0.0.0/24"], ["9.0.0.0/8", "10.0.0.0/8"]), [])
        self.assertEqual(split.subtract(["10.0.0.0/24", "2a00::/16"], ["11.0.0.0/8"]), ["10.0.0.0/24", "2a00::/16"])
        self.assertEqual(split.subtract(["10.0.0.0/30"], ["10.0.0.1", "10.0.0.2"]), ["10.0.0.0/32", "10.0.0.3/32"])

    def test_geo_direct_keeps_blocked_and_games(self):
        # «страна» 10.0.0.0/8: база содержит 10.1.0.0/16…, iRacing 10.5.0.0/16 через запрет
        fake = {"ipv4": "10.0.0.0/8\n77.0.0.0/8\n", "ipv6": "2a00::/16\n"}
        fetch = lambda url: fake["ipv4" if "ipv4" in url else "ipv6"]
        split.fetch_geo("XX", fetch)  # дальше add_rule возьмёт кеш, сеть не нужна
        split.add_rule(self.z, "XX", "direct", kind="geo")
        excl = self.lines("ipset-exclude-user.txt")
        self.assertIn("77.0.0.0/8", excl)
        self.assertIn("2a00::/16", excl)
        self.assertEqual(split.coverage(["10.1.0.0/16", "10.5.0.0/16", "3.2.66.0/23"], excl), 0)  # заблокированное и игра не исключены
        self.assertEqual(split.coverage(["10.0.0.0/16", "10.200.0.0/16"], excl), 2)  # остальное — исключено
        rule = [r for r in split.snapshot(self.z)["rules"] if r["kind"] == "geo"][0]
        self.assertEqual(rule["kept_blocked"], 199)

    def test_profile_domains_and_asns(self):
        payload = json.dumps({"data": {"prefixes": [{"prefix": "45.0.0.0/22"}, {"prefix": "2a01:1::/32"}]}})
        split.fetch_asn(64500, lambda u: payload)  # кеш AS64500, add_profile не пойдёт в сеть
        p = split.add_profile(self.z, "Apex", "", route="zapret", domains="ea.com\nhttps://www.respawn.com/x", asns="AS64500")
        self.assertEqual(p.domains, ["ea.com", "www.respawn.com"])
        self.assertIn("45.0.0.0/22", self.lines("ipset-all.txt"))
        self.assertIn("ea.com", self.lines("list-general-user.txt"))
        split.update_profile(self.z, p.id, {"route": "direct"})
        self.assertIn("ea.com", self.lines("list-exclude-user.txt"))
        self.assertIn("45.0.0.0/22", self.lines("ipset-exclude-user.txt"))
        with self.assertRaises(split.SplitError):
            split.update_profile(self.z, p.id, {"asns": "AS12x"})

    def test_iracing_bootstrap_has_domain(self):
        prof = split.snapshot(self.z)["profiles"][0]
        self.assertEqual((prof["domains"], prof["preset"]), (["iracing.com"], "iracing"))
        self.assertEqual(prof["asns"], [397127, 398123])
        self.assertEqual(prof["asn_counts"], {"397127": 0, "398123": 0})  # кеш ASN пуст — сеть в тестах не трогаем
        split.update_profile(self.z, prof["id"], {"route": "zapret"})
        self.assertIn("iracing.com", self.lines("list-general-user.txt"))

    def test_rules_go_to_right_files(self):
        split.add_rule(self.z, "https://unblocked.example.com/x", "direct")
        split.add_rule(self.z, "5.6.7.8", "direct")
        split.add_rule(self.z, "203.0.0.0/24", "zapret")
        self.assertIn("unblocked.example.com", self.lines("list-exclude-user.txt"))
        self.assertNotIn("domain.example.abc", self.lines("list-exclude-user.txt"))
        self.assertIn("my-blocked.org", self.lines("list-general-user.txt"))
        excl = self.lines("ipset-exclude-user.txt")
        self.assertEqual(excl[0], zapret.PLACEHOLDER_IP)
        self.assertIn("5.6.7.8", excl)
        self.assertIn("203.0.0.0/24", self.lines("ipset-all.txt"))
        self.assertIn("203.0.0.0/24", self.lines("ipset-all.txt.backup"))

    def test_profile_direct_and_off(self):
        pid = split.snapshot(self.z)["profiles"][0]["id"]
        split.update_profile(self.z, pid, {"route": "direct"})
        self.assertIn("3.2.66.0/23", self.lines("ipset-exclude-user.txt"))
        self.assertNotIn("3.2.66.0/23", self.lines("ipset-all.txt"))
        split.update_profile(self.z, pid, {"route": "off"})
        self.assertEqual(self.lines("ipset-exclude-user.txt"), [zapret.PLACEHOLDER_IP])
        self.assertNotIn("3.2.66.0/23", self.lines("ipset-all.txt"))
        self.assertIn("10.5.0.0/16", self.lines("ipset-all.txt"))  # база не потеряна

    def test_user_files_never_empty(self):
        rid = split.snapshot(self.z)["rules"][0]["id"]
        split.delete_rule(self.z, rid)
        split.update_profile(self.z, split.snapshot(self.z)["profiles"][0]["id"], {"route": "off"})
        self.assertEqual(self.lines("list-general-user.txt"), ["domain.example.abc"])
        self.assertTrue(self.lines("list-exclude-user.txt"))
        self.assertTrue(self.lines("ipset-exclude-user.txt"))

    def test_ipset_modes(self):
        split.add_rule(self.z, "203.0.0.0/24", "zapret")
        split.set_ipset_mode(self.z, "none")
        self.assertEqual(zapret.ipset_mode(self.z), "none")
        self.assertIn("203.0.0.0/24", self.lines("ipset-all.txt.backup"))
        split.add_rule(self.z, "198.51.100.0/24", "zapret")  # в режиме none ipset-all не раздувается
        self.assertEqual(zapret.ipset_mode(self.z), "none")
        split.set_ipset_mode(self.z, "any")
        self.assertEqual(zapret.ipset_mode(self.z), "any")
        split.set_ipset_mode(self.z, "loaded")
        self.assertIn("198.51.100.0/24", self.lines("ipset-all.txt"))

    def test_external_ipset_update_survives_mode_switch(self):
        # обновили IPSet через service.bat, потом подбор переключил режим в «Все» и обратно
        split.apply(self.z)
        (self.z / "lists" / "ipset-all.txt").write_text("100.0.0.0/8\n", encoding="utf-8")
        split.set_ipset_mode(self.z, "any")
        split.set_ipset_mode(self.z, "loaded")
        self.assertIn("100.0.0.0/8", self.lines("ipset-all.txt"))

    def test_external_ipset_update_becomes_base(self):
        split.apply(self.z)
        (self.z / "lists" / "ipset-all.txt").write_text("100.0.0.0/8\n", encoding="utf-8")  # service.bat «Update IPSet»
        split.add_rule(self.z, "a.example.com", "direct")
        all_lines = self.lines("ipset-all.txt")
        self.assertIn("100.0.0.0/8", all_lines)
        self.assertIn("3.2.66.0/23", all_lines)  # iRacing вмёржен заново

    def test_custom_profile(self):
        with self.assertRaises(split.SplitError):
            split.add_profile(self.z, "ACC", "1.2.3.0/24\nмусор")
        split.add_profile(self.z, "Assetto Corsa", "1.2.3.0/24\n# comment\n", route="direct")
        prof = [p for p in split.snapshot(self.z)["profiles"] if p["name"] == "Assetto Corsa"][0]
        self.assertEqual(prof["file"], "ipset-assetto-corsa.txt")
        self.assertIn("1.2.3.0/24", self.lines("ipset-exclude-user.txt"))
        split.delete_profile(self.z, prof["id"])
        self.assertFalse((self.z / "lists" / "ipset-assetto-corsa.txt").exists())

    def test_originals_backed_up_once(self):
        split.apply(self.z)
        b = self.data / "backups" / "lists-original" / "list-general-user.txt"
        self.assertIn("my-blocked.org", b.read_text(encoding="utf-8"))


class UpdaterTests(TempCase):
    def test_failed_zapret_update_brings_service_back(self):
        rel = {"version": "9.9", "assets": [{"name": "z.zip", "url": "u", "sha256": None}]}
        job = updater.Job("update")
        with mock.patch.object(updater, "_cached_release", return_value=rel),              mock.patch.object(updater, "download", return_value=self.tmp / "z.zip"),              mock.patch.object(updater, "safe_extract", return_value=self.tmp / "zapret-9.9" / "root"),              mock.patch.object(updater, "plan_files", return_value=([], [])),              mock.patch.object(updater, "install_files", side_effect=OSError("файл занят")),              mock.patch.object(zapret, "service_state", return_value="running"),              mock.patch.object(zapret, "installed_strategy", return_value="general"),              mock.patch.object(zapret, "stop_all"),              mock.patch.object(winutil, "process_running", return_value=False),              mock.patch.object(zapret, "start_service") as start:
            with self.assertRaises(OSError):
                updater.update_zapret(job, self.z, None)
        start.assert_called_once()  # запрет не остался выключенным

    def test_versions(self):
        self.assertTrue(updater.is_newer("1.10.5", "1.10.4"))
        self.assertTrue(updater.is_newer("v1.12.0", "v1.11.4"))
        self.assertTrue(updater.is_newer("1.11", "1.10.9"))
        self.assertFalse(updater.is_newer("1.10.4", "1.10.4"))
        self.assertFalse(updater.is_newer("1.10.4", "1.10.10"))
        self.assertFalse(updater.is_newer("1.10.4.0", "1.10.4"))
        self.assertTrue(updater.is_newer("1.0", None))

    def make_release(self) -> Path:
        rel = Path(tempfile.mkdtemp(dir=self.tmp)) / "zapret-discord-youtube-1.11.0"
        (rel / "bin").mkdir(parents=True)
        (rel / "lists").mkdir()
        (rel / "utils").mkdir()
        (rel / "bin" / "winws.exe").write_bytes(b"new-winws")
        (rel / "service.bat").write_text('set "LOCAL_VERSION=1.11.0"\n', encoding="utf-8")
        (rel / "general (NEW).bat").write_text(BAT, encoding="utf-8")
        (rel / "lists" / "ipset-all.txt").write_text(zapret.PLACEHOLDER_IP + "\n", encoding="utf-8")
        (rel / "lists" / "ipset-all.txt.backup").write_text("1.0.0.0/24\n", encoding="utf-8")
        (rel / "lists" / "list-general.txt").write_text("new.example\n", encoding="utf-8")
        (rel / "utils" / "check_updates.enabled").write_text("ENABLED\n", encoding="utf-8")
        return rel

    def test_plan_preserves_user_files(self):
        copy, keep = updater.plan_files(self.make_release())
        self.assertIn("bin/winws.exe", copy)
        self.assertIn("lists/list-general.txt", copy)
        self.assertEqual(sorted(keep), ["lists/ipset-all.txt", "lists/ipset-all.txt.backup", "utils/check_updates.enabled"])

    def test_install_and_rollback(self):
        rel = self.make_release()
        copy, _ = updater.plan_files(rel)
        before_user = (self.z / "lists" / "list-general-user.txt").read_bytes()
        updater.install_files(rel, self.z, copy, self.data / "b1.zip")
        self.assertEqual((self.z / "bin" / "winws.exe").read_bytes(), b"new-winws")
        self.assertEqual(zapret.local_version(self.z), "1.11.0")
        self.assertEqual((self.z / "lists" / "list-general-user.txt").read_bytes(), before_user)
        self.assertEqual(zapret.ipset_mode(self.z), "loaded")
        self.assertFalse((self.z / "utils" / "check_updates.enabled").exists())  # пользователь его выключал

        # ошибка посреди копирования -> всё возвращается
        rel2 = self.make_release()
        (rel2 / "bin" / "winws.exe").write_bytes(b"newer")
        real_copy = shutil.copy2

        def flaky(src, dst, *a, **k):
            if "service.bat" in str(src):
                raise OSError("диск отвалился")
            return real_copy(src, dst, *a, **k)

        with mock.patch.object(updater.shutil, "copy2", flaky), self.assertRaises(OSError):
            updater.install_files(rel2, self.z, copy, self.data / "b2.zip")
        self.assertEqual((self.z / "bin" / "winws.exe").read_bytes(), b"new-winws")

    def test_install_rollback_removes_new_files(self):
        rel = self.make_release()
        copy, _ = updater.plan_files(rel)

        def boom(src, dst, *a, **k):
            if "winws" in str(src):
                raise OSError("x")
            return shutil.copyfile(src, dst)

        with mock.patch.object(updater.shutil, "copy2", boom), self.assertRaises(OSError):
            updater.install_files(rel, self.z, copy, self.data / "b.zip")
        self.assertFalse((self.z / "general (NEW).bat").exists())
        self.assertEqual((self.z / "bin" / "winws.exe").read_bytes(), b"old-winws")

    def test_safe_extract(self):
        good = self.tmp / "good.zip"
        rel = self.make_release()
        with zipfile.ZipFile(good, "w") as z:
            for f in rel.rglob("*"):
                if f.is_file():
                    z.write(f, f"zapret-discord-youtube-1.11.0/{f.relative_to(rel).as_posix()}")
        root = updater.safe_extract(good, self.tmp / "x")
        self.assertTrue((root / "bin" / "winws.exe").exists())

        evil = self.tmp / "evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../../evil.txt", "x")
        with self.assertRaises(updater.UpdateError):
            updater.safe_extract(evil, self.tmp / "y")


class VersionTests(unittest.TestCase):
    def test_versions_agree(self):
        import tomllib
        import app
        root = Path(__file__).resolve().parent.parent
        py = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        js = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))["version"]
        rs = tomllib.loads((root / "desktop" / "Cargo.toml").read_text(encoding="utf-8"))["package"]["version"]
        tauri = json.loads((root / "desktop" / "tauri.conf.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual((app.__version__, js, rs, tauri), (py, py, py, py))


class ApiGuardTests(unittest.TestCase):
    def call(self, path, headers, method="GET", body=b""):
        from app.api import app
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
                 "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
                 "root_path": "", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                 "client": ("127.0.0.1", 5000), "server": ("127.0.0.1", 47800)}
        sent = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(msg):
            sent.append(msg)

        asyncio.run(app(scope, receive, send))
        start = next(m for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return start["status"], body

    def test_guard(self):
        from app.api import TOKEN
        self.assertEqual(self.call("/api/settings", {"host": "evil.com"})[0], 403)  # DNS rebinding
        self.assertEqual(self.call("/api/settings", {"host": "127.0.0.1:47800"})[0], 403)  # без токена
        self.assertEqual(self.call("/api/settings", {"host": "127.0.0.1:47800", "x-pipo-token": "nope"})[0], 403)
        status, body = self.call("/api/settings", {"host": "127.0.0.1:47800", "x-pipo-token": TOKEN})
        self.assertEqual(status, 200)
        self.assertIn("zapret_dir", json.loads(body))
        status, body = self.call("/", {"host": "localhost:47800"})
        self.assertEqual(status, 200)
        self.assertIn(TOKEN.encode(), body)

    def test_changes_refused_while_job_runs(self):
        from app import jobs
        from app.api import TOKEN
        h = {"host": "127.0.0.1:47800", "x-pipo-token": TOKEN}
        job = jobs.Job("scan")
        with mock.patch.object(jobs, "current", return_value=job):
            status, body = self.call("/api/zapret/start", h, "POST")
            self.assertEqual(status, 409)
            self.assertIn("подбор", json.loads(body)["detail"])
            self.assertEqual(self.call("/api/settings", h)[0], 200)  # читать можно
            self.assertNotEqual(self.call(f"/api/jobs/{job.id}/cancel", h, "POST")[0], 409)  # остановить — тоже

    def test_ui_theme_saved_for_shell(self):
        """Тему видит окно-оболочка в settings.json ещё до старта сервера; менять её можно и во время подбора."""
        from app import jobs
        from app.api import TOKEN
        h = {"host": "127.0.0.1:47800", "x-pipo-token": TOKEN, "content-type": "application/json"}
        data = Path(tempfile.mkdtemp(prefix="pipo-test-"))
        self.addCleanup(shutil.rmtree, data, True)
        with mock.patch.object(app_settings, "DATA_DIR", data),                 mock.patch.object(jobs, "current", return_value=jobs.Job("scan")):
            self.assertEqual(app_settings.load()["ui_theme"], "system")
            status, _ = self.call("/api/ui", h, "PUT", json.dumps({"theme": "light"}).encode())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads((data / "settings.json").read_text(encoding="utf-8"))["ui_theme"], "light")
            self.assertEqual(self.call("/api/ui", h, "PUT", b'{"theme": "pink"}')[0], 400)
            status, body = self.call("/api/ui", h, "PUT", json.dumps({"scale": "1.25", "tour_done": True}).encode())
            self.assertEqual(json.loads(body), {"theme": "light", "scale": "1.25", "tour_done": True})
            for bad in ({"scale": 1.25}, {"tour_done": 1}, {"zoom": "1"}):
                self.assertEqual(self.call("/api/ui", h, "PUT", json.dumps(bad).encode())[0], 400, bad)


class ShellPortTests(unittest.TestCase):
    def test_busy_port_from_shell_exits_with_code(self):
        """Порт от оболочки занят — сервер не уходит молча на соседний, а сообщает кодом 3 (оболочка выберет другой)."""
        import os
        import socket
        import subprocess
        import sys
        import main
        root = Path(__file__).resolve().parent.parent
        data = Path(tempfile.mkdtemp(prefix="pipo-test-"))
        self.addCleanup(shutil.rmtree, data, True)
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            env = {**os.environ, "PIPO_DATA_DIR": str(data), "PIPO_TOKEN": "t"}
            r = subprocess.run([sys.executable, str(root / "main.py"), "--server-only", "--no-admin",
                                "--port", str(port), "--parent-pid", str(os.getpid())],
                               env=env, cwd=root, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, main.EXIT_PORT_BUSY, r.stderr.decode(errors="replace")[-500:])


if __name__ == "__main__":
    unittest.main()
