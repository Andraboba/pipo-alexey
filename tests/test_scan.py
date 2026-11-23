from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from app import scan, split, zapret
from app.jobs import Job
from tests.test_core import TempCase


class ParseTests(unittest.TestCase):
    def test_custom_targets(self):
        got = [(t["kind"], t.get("host") or t.get("url"), t.get("port")) for t in scan.parse_custom(
            "# комментарий\n1.1.1.1\n8.8.8.8:53\n[2a03:2880::1]:8443\n2a03:2880::1\nexample.com\nhttps://x.org/a\n")]
        self.assertEqual(got, [
            ("ip", "1.1.1.1", 443), ("ip", "8.8.8.8", 53), ("ip", "2a03:2880::1", 8443), ("ip", "2a03:2880::1", 443),
            ("url", "https://example.com", None), ("url", "https://x.org/a", None),
        ])

    def test_grade_ignores_dead_and_tls13_ceiling(self):
        """Случай из жизни: Discord заблокирован, tnt-ea.com не резолвится нигде,
        iracing.com везде «наполовину» (нет TLS 1.3 на сервере)."""
        r = lambda s: {"score": s, "detail": "", "ms": 100}
        targets = [{"id": i, "name": i} for i in ("discord", "dead", "iracing")]
        res = {
            "targets": targets,
            "baseline": {"discord": r(0), "dead": r(0), "iracing": r(0.5)},
            "rows": [
                {"strategy": "ALT", "state": "done", "ms": 300, "results": {"discord": r(1), "dead": r(0), "iracing": r(0.5)}},
                {"strategy": "BAD", "state": "done", "ms": 300, "results": {"discord": r(0), "dead": r(0), "iracing": r(0)}},
            ],
        }
        scan.grade(res)
        self.assertEqual({k: v["status"] for k, v in res["meta"].items()}, {"discord": "blocked", "dead": "dead", "iracing": "open"})
        alt, bad = res["rows"]
        self.assertEqual((alt["score"], alt["of"], alt["grade"], alt["fixed"], alt["broke"]), (2, 2, "ideal", 1, 0))
        self.assertEqual((bad["score"], bad["grade"], bad["broke"]), (0, "broken", 1))  # сломала открытый iracing
        self.assertEqual(res["best"], "ALT")

    def test_game_targets_are_real_hosts(self):
        from app import presets
        self.assertTrue(all(p.get("probe") for p in presets.PRESETS))
        self.assertIn("members-ng.iracing.com", presets.get("iracing")["probe"])

    def test_dpi_freeze_detection(self):
        t = {"host": "x"}
        with mock.patch.object(scan, "_run_curl", return_value=(28, f"000 65536 0 {scan.DPI_TIMEOUT}.01", "")):
            self.assertEqual(scan.check_dpi(t, Path("p"))["score"], 0)
        with mock.patch.object(scan, "_run_curl", return_value=(0, "200 65536 4096 0.4", "")):
            self.assertEqual(scan.check_dpi(t, Path("p"))["score"], 1)

    def test_url_freeze_after_handshake_is_failure(self):
        """HEAD отвечает (рукопожатие и короткий ответ пропущены), а 64 КБ замерзают —
        так у ТСПУ выглядит «Discord зелёный в подборе, но не грузится»."""
        head = (0, "404", "")
        frozen = (28, f"000 65536 0 {scan.DPI_TIMEOUT}.01", "")
        with mock.patch.object(scan, "_run_curl", side_effect=[head, head, frozen]):
            r = scan.check_url({"url": "https://x"}, Path("p"))
        self.assertEqual(r["score"], 0)
        self.assertIn("заморозка", r["detail"])
        with mock.patch.object(scan, "_run_curl", side_effect=[head, head, (0, "405 65536 120 0.3", "")]):
            self.assertEqual(scan.check_url({"url": "https://x"}, Path("p"))["score"], 1)
        # сброс соединения на большом POST — не заморозка: сайт не наказываем
        with mock.patch.object(scan, "_run_curl", side_effect=[head, head, (56, "000 16384 0 0.2", "")]):
            self.assertEqual(scan.check_url({"url": "https://x"}, Path("p"))["score"], 1)

    def test_url_freeze_probe_skipped_when_site_failed(self):
        with mock.patch.object(scan, "_run_curl", return_value=(28, "", "timeout")) as run:
            self.assertEqual(scan.check_url({"url": "https://x"}, Path("p"))["score"], 0)
        self.assertEqual(run.call_count, 2)  # только два HEAD, POST не тратим

    def test_url_cert_substitution_is_failure(self):
        with mock.patch.object(scan, "_run_curl", return_value=(60, "", "SSL certificate problem: self-signed")):
            r = scan.check_url({"url": "https://x"})
        self.assertEqual(r["score"], 0)
        self.assertIn("подмена", r["detail"])


class RunScanTests(TempCase):
    def run_with(self, check_results, start_fail=()):
        targets = [{"id": "a", "name": "a", "kind": "url", "url": "https://a"}, {"id": "b", "name": "b", "kind": "url", "url": "https://b"}]
        calls = iter(check_results)
        job = Job("scan")

        def fake_check(*_):
            v = next(calls)
            if isinstance(v, Exception):
                raise v
            return v

        def fake_start(zdir, strategy):
            if strategy in start_fail:
                raise scan.ScanError("winws завершился с кодом 1")
            return None

        with mock.patch.object(scan.CURL.__class__, "exists", return_value=True), \
             mock.patch.object(scan, "check_all", side_effect=fake_check), \
             mock.patch.object(scan, "start_winws", side_effect=fake_start), \
             mock.patch.object(scan, "stop_winws"), \
             mock.patch.object(zapret, "stop_all"), \
             mock.patch.object(zapret, "service_state", return_value="running"), \
             mock.patch.object(zapret, "start_service") as start_service:
            res = scan.run_scan(job, self.z, ["general", "general (ALT)"], targets)
        return res, job, start_service

    def test_ranks_and_restores(self):
        ok = {"score": 1, "detail": "", "ms": 100}
        bad = {"score": 0, "detail": "", "ms": 4000}
        res, job, start_service = self.run_with([
            {"a": bad, "b": ok},   # без запрета
            {"a": ok, "b": bad},   # general
            {"a": ok, "b": ok},    # ALT
        ])
        self.assertEqual(res["best"], "general (ALT)")
        self.assertEqual({r["strategy"]: r["grade"] for r in res["rows"]}, {"general": "partial", "general (ALT)": "ideal"})
        self.assertEqual(zapret.ipset_mode(self.z), "loaded")  # IPSet вернулся
        start_service.assert_called_once()  # служба работала до подбора — запущена снова
        self.assertEqual(scan.load_last()["best"], "general (ALT)")

    def test_broken_strategy_and_restore_on_error(self):
        ok = {"score": 1, "detail": "", "ms": 100}
        res, _, start_service = self.run_with([{"a": ok, "b": ok}, {"a": ok, "b": ok}], start_fail=("general",))
        self.assertEqual(res["rows"][0]["state"], "failed")
        self.assertEqual(res["best"], "general (ALT)")
        # ошибка посреди проверки: всё равно возвращаем IPSet и службу
        with self.assertRaises(RuntimeError):
            self.run_with([{"a": ok, "b": ok}, RuntimeError("boom")])
        self.assertEqual(zapret.ipset_mode(self.z), "loaded")


if __name__ == "__main__":
    unittest.main()
