"""Второй движок: zapret2 (winws2.exe, сборка kinlay0) рядом с Flowseal."""
from __future__ import annotations

import zipfile
from unittest import mock

from app import scan, settings, split, switch, updater, zapret
from tests.test_core import TempCase

# как в сборке kinlay0: блоки опций разделены пустыми строками, пути относительно bin
BAT2 = r'''@echo off
set "BIN=%~dp0bin\"
set "LISTS=..\lists\"
set "LUA=..\lua\"
cd /d "%BIN%"

start "zapret: %~n0" /min "%BIN%winws2.exe" --wf-tcp-out=80,443,%GameFilterTCP% --wf-udp-out=443,%GameFilterUDP% ^

--lua-init=@"%LUA%zapret-lib.lua" ^
--lua-init=@"%LUA%zapret-antidpi.lua" ^

--name="domain tls" ^
--filter-tcp=80,443 ^
--hostlist="%LISTS%list-general.txt" ^
--payload=tls_client_hello ^
--lua-desync=fake:blob=tls_google:repeats=6 ^
--lua-desync=multisplit:pos=2
'''


class Zapret2Case(TempCase):
    def setUp(self):
        super().setUp()
        self.z2 = self.tmp / "Zapret2"
        for d in ("bin", "lists", "lua", "utils"):
            (self.z2 / d).mkdir(parents=True)
        (self.z2 / "bin" / "winws2.exe").write_bytes(b"winws2")
        (self.z2 / "service.bat").write_text('@echo off\nset "LOCAL_VERSION=1.1.5"\n', encoding="utf-8")
        (self.z2 / "general (SIMPLE FAKE).bat").write_text(BAT2, encoding="utf-8")
        (self.z2 / "general (ALT14).bat").write_text(BAT2, encoding="utf-8")
        (self.z2 / "lists" / "ipset-all.txt").write_text("192.0.2.0/24\n", encoding="utf-8")
        settings.save({"zapret_dir": str(self.z), "zapret2_dir": str(self.z2)})


class EngineDetectTests(Zapret2Case):
    def test_engine_by_exe(self):
        self.assertEqual(zapret.engine_of(self.z).id, "flowseal")
        self.assertEqual(zapret.engine_of(self.z2).id, "zapret2")
        self.assertEqual(zapret.winws_exe(self.z2).name, "winws2.exe")

    def test_empty_dir_by_settings(self):
        empty = self.tmp / "New2"
        settings.save({"zapret2_dir": str(empty)})
        self.assertEqual(zapret.engine_of(empty).id, "zapret2")

    def test_active_dir_follows_engine(self):
        self.assertEqual(settings.zapret_dir(), self.z)
        settings.save({"engine": "zapret2"})
        self.assertEqual(settings.zapret_dir(), self.z2)


class Zapret2ArgsTests(Zapret2Case):
    def test_blank_lines_lua_and_absolute_paths(self):
        args = zapret.build_args(self.z2, "general (SIMPLE FAKE)", zapret.GameFilter("tcp", "1024-65535"))
        root = str(self.z2) + "\\"
        self.assertIn(f"--lua-init=@{root}lua\\zapret-lib.lua", args)
        self.assertIn(f"--hostlist={root}lists\\list-general.txt", args)
        self.assertIn('--name="domain tls"', args)  # пробел внутри — кавычки остаются
        self.assertEqual(args[-1], "--lua-desync=multisplit:pos=2")  # пустые строки не обрывают команду
        self.assertIn("--wf-tcp-out=80,443,1024-65535", args)
        self.assertIn("--wf-udp-out=443,12", args)
        self.assertFalse([a for a in args if "..\\" in a or "%" in a])
        self.assertEqual(args[0], "--chdir")  # иначе служба из System32 не найдёт фейки blobs.lua

    def test_bin_path_uses_winws2(self):
        self.assertTrue(zapret.build_bin_path(self.z2, "general (ALT14)", zapret.GameFilter()).startswith(
            f'"{self.z2 / "bin" / "winws2.exe"}" '))


class SwitchTests(Zapret2Case):
    def run_switch(self, engine, state="running", strategy="general"):
        calls = {}
        with mock.patch.object(zapret, "service_state", return_value=state), \
             mock.patch.object(zapret, "installed_strategy", return_value=strategy), \
             mock.patch.object(zapret, "stop_all") as stop, \
             mock.patch.object(zapret, "install_service") as install:
            res = switch.switch(engine, lambda *a, **k: None)
        calls["stop"], calls["install"] = stop, install
        return res, calls

    def test_switch_to_zapret2_and_back(self):
        (self.z / "lists" / "ipset-apex.txt").write_text("198.51.100.0/24\n", encoding="utf-8")
        res, c = self.run_switch("zapret2")
        c["stop"].assert_called_once_with(stop_driver=True)
        self.assertEqual(settings.engine(), "zapret2")
        # стратегии «general» у zapret2 нет — первая по порядку service.bat
        c["install"].assert_called_once_with(self.z2, "general (ALT14)", start=True)
        self.assertTrue(res["started"])
        # игровой фильтр и ручные подсети игр переехали, сплит наложен на списки zapret2
        self.assertEqual(zapret.read_game_filter(self.z2).mode, "all")
        self.assertTrue((self.z2 / "lists" / "ipset-apex.txt").is_file())
        self.assertTrue((self.z2 / "lists" / "list-general-user.txt").is_file())

        res, c = self.run_switch("flowseal", state="stopped", strategy="general (ALT14)")
        self.assertEqual(settings.engine(), "flowseal")
        c["install"].assert_called_once_with(self.z, "general", start=False)  # своя прежняя стратегия

    def test_switch_without_service_does_not_install(self):
        res, c = self.run_switch("zapret2", state=None, strategy=None)
        c["install"].assert_not_called()
        self.assertEqual(settings.engine(), "zapret2")

    def test_switch_keeps_ipset_mode_and_base(self):
        split.apply(self.z)
        split.set_ipset_mode(self.z, "any")
        base = split.read_list(split.base_file())
        self.run_switch("zapret2")
        self.assertEqual(zapret.ipset_mode(self.z2), "any")
        # ipset-all из релиза zapret2 — не «обновление списка», базу не подменяет
        self.assertEqual(split.read_list(split.base_file()), base)

    def test_not_installed_refused(self):
        (self.z2 / "bin" / "winws2.exe").unlink()
        with self.assertRaises(switch.SwitchError):
            self.run_switch("zapret2")
        self.assertEqual(settings.engine(), "flowseal")

    def test_settings_cannot_switch_engine(self):
        from app import api
        api.settings_put({"engine": "zapret2", "strategies": {"x": 1}})
        self.assertEqual(settings.engine(), "flowseal")


class Zapret2UpdateTests(Zapret2Case):
    def test_safe_extract_wants_winws2(self):
        zp = self.tmp / "r.zip"
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("service.bat", "x")
            z.writestr("bin/winws2.exe", "x")
        self.assertTrue((updater.safe_extract(zp, self.tmp / "x", "winws2.exe") / "bin" / "winws2.exe").is_file())
        with self.assertRaises(updater.UpdateError):
            updater.safe_extract(zp, self.tmp / "y", "winws.exe")

    def test_fresh_install_of_inactive_engine_does_not_touch_service(self):
        target = self.tmp / "Fresh2"
        settings.save({"zapret2_dir": str(target)})
        zp = self.tmp / "z2.zip"
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("service.bat", 'set "LOCAL_VERSION=1.1.5"')
            z.writestr("bin/winws2.exe", "x")
            z.writestr("lists/ipset-all.txt", "192.0.2.0/24\n")  # «пользовательский», но при первой установке нужен
            z.writestr("general (SIMPLE FAKE).bat", BAT2)
        rel = {"version": "1.1.5", "assets": [{"name": "z2.zip", "url": "u", "sha256": None}]}
        with mock.patch.object(updater, "_cached_release", return_value=rel), \
             mock.patch.object(updater, "download", return_value=zp), \
             mock.patch.object(zapret, "stop_all") as stop:
            updater.update_zapret(updater.Job("zapret2"), target, None, "zapret2")
        stop.assert_not_called()  # работает Flowseal — его не трогаем
        self.assertTrue((target / "bin" / "winws2.exe").is_file())
        self.assertTrue((target / "lists" / "ipset-all.txt").is_file())
        self.assertEqual(zapret.list_strategies(target), ["general (SIMPLE FAKE)"])


class ScanLastTests(Zapret2Case):
    def test_last_result_per_engine(self):
        scan.save_last({"engine": "zapret2", "best": "general (ALT14)"})
        scan.save_last({"engine": "flowseal", "best": "general"})
        self.assertEqual(scan.load_last("zapret2")["best"], "general (ALT14)")
        self.assertEqual(scan.load_last("flowseal")["best"], "general")


class SwitchRollbackTests(Zapret2Case):
    def test_failed_install_returns_old_engine(self):
        with mock.patch.object(zapret, "service_state", return_value="running"), \
             mock.patch.object(zapret, "installed_strategy", return_value="general"), \
             mock.patch.object(zapret, "stop_all"), \
             mock.patch.object(zapret, "install_service", side_effect=[zapret.ServiceError("sc create: отказано"), None]) as inst:
            with self.assertRaises(switch.SwitchError):
                switch.switch("zapret2", lambda *a, **k: None)
        self.assertEqual(settings.engine(), "flowseal")
        inst.assert_called_with(self.z, "general", start=True)  # прежняя служба вернулась и запущена

    def test_no_strategies_refused_before_stopping(self):
        for f in self.z2.glob("*.bat"):
            if f.name != "service.bat":
                f.unlink()
        with mock.patch.object(zapret, "service_state", return_value="running"), \
             mock.patch.object(zapret, "installed_strategy", return_value="general"), \
             mock.patch.object(zapret, "stop_all") as stop:
            with self.assertRaises(switch.SwitchError):
                switch.switch("zapret2", lambda *a, **k: None)
        stop.assert_not_called()  # запрет даже не останавливали


class Zapret2ApiTests(Zapret2Case):
    def test_evolve_save_refused_for_flowseal(self):
        from fastapi import HTTPException
        from app import api
        with self.assertRaises(HTTPException) as e, mock.patch.object(api.winutil, "is_admin", return_value=True):
            api.evolve_save("x")
        self.assertEqual(e.exception.status_code, 409)

    def test_same_folder_for_both_engines_refused(self):
        from fastapi import HTTPException
        from app import api
        with self.assertRaises(HTTPException):
            api.settings_put({"zapret2_dir": str(self.z)})
