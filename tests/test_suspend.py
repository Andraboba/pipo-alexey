"""Пауза запрета: что бы ни случилось внутри, запрет и IPSet возвращаются."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import settings as app_settings
from app import split, suspend, winutil, zapret
from tests.test_core import make_zapret


class SuspendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pipo-suspend-"))
        self.z = make_zapret(self.tmp)
        data = self.tmp / "data"
        self.log: list[tuple[str, str]] = []
        self.patches = [mock.patch.object(m, "DATA_DIR", data) for m in (split, suspend, app_settings)]
        self.patches += [
            mock.patch.object(zapret, "stop_all"),
            mock.patch.object(winutil, "process_running", return_value=False),
        ]
        for p in self.patches:
            p.start()
        split.apply(self.z)  # IPSet в «loaded»

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def say(self, text, level="info"):
        self.log.append((level, text))

    def test_service_comes_back_even_if_ipset_restore_fails(self):
        real = split.set_ipset_mode
        calls = iter([real, mock.Mock(side_effect=OSError("диск занят"))])
        with mock.patch.object(zapret, "service_state", return_value="running"), \
             mock.patch.object(zapret, "start_service") as start, \
             mock.patch.object(split, "set_ipset_mode", side_effect=lambda *a: next(calls)(*a)):
            with self.assertRaises(RuntimeError):
                with suspend.suspended(self.z, self.say, ipset="any"):
                    raise RuntimeError("подбор упал")
        start.assert_called_once()
        self.assertIn(("error", "Не удалось вернуть режим IPSet: диск занят"), self.log)

    def test_starting_service_is_restarted(self):
        with mock.patch.object(zapret, "service_state", return_value="start_pending"), \
             mock.patch.object(zapret, "start_service") as start:
            with suspend.suspended(self.z, self.say):
                pass
        start.assert_called_once()

    def test_bat_winws_user_is_warned(self):
        with mock.patch.object(zapret, "service_state", return_value=None), \
             mock.patch.object(winutil, "process_running", return_value=True), \
             mock.patch.object(zapret, "start_service") as start:
            with suspend.suspended(self.z, self.say):
                pass
        start.assert_not_called()
        self.assertTrue(any(level == "warn" and ".bat" in text for level, text in self.log))

    def test_recover_after_app_was_closed_mid_scan(self):
        with mock.patch.object(zapret, "service_state", return_value="running"), \
             mock.patch.object(zapret, "start_service") as start:
            cm = suspend.suspended(self.z, self.say, ipset="any")
            cm.__enter__()  # окно закрыли — finally так и не выполнился
            self.assertEqual(zapret.ipset_mode(self.z), "any")
            start.assert_not_called()

            zapret.stop_all.reset_mock()
            self.assertTrue(suspend.recover(self.say))
            zapret.stop_all.assert_called()  # winws прерванного подбора не должен жить рядом со службой
            self.assertEqual(zapret.ipset_mode(self.z), "loaded")
            start.assert_called_once()
            self.assertFalse(suspend.recover(self.say))  # журнал убран, второй раз не возвращаем

    def test_clean_exit_leaves_no_journal(self):
        with mock.patch.object(zapret, "service_state", return_value="stopped"):
            with suspend.suspended(self.z, self.say, ipset="any"):
                pass
        self.assertEqual(zapret.ipset_mode(self.z), "loaded")
        self.assertFalse(suspend.recover(self.say))


if __name__ == "__main__":
    unittest.main()
