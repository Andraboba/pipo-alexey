"""Эволюция стратегий на «игрушечном DPI»: без winws2 и сети."""
from __future__ import annotations

import random
import unittest
from pathlib import Path

from app import evolve, zapret
from app.evolve import Step, parse_step
from app.jobs import Job
from tests.test_engines import Zapret2Case

TARGETS = ["blocked1", "blocked2", "open1"]
BASELINE = {"blocked1": 0.0, "blocked2": 0.0, "open1": 1.0}


def toy_dpi(g):
    """Пробивает фейк с tcp_md5 перед разрезанием посередине домена (midsld); фейк без обмана ломает открытый сайт."""
    fakes = [s for s in g if s.func == "fake"]
    term = g[-1] if g[-1].func != "fake" else None
    ok = any(s.get("fool") == "tcp_md5" for s in fakes) and term and term.func in ("multisplit", "multidisorder") \
        and "midsld" in term.get("pos")
    half = any(s.get("fool") == "tcp_md5" for s in fakes)  # одна половина (TLS 1.2) проходит уже от фейка
    broke = any(s.get("fool") == "" for s in fakes)
    score = 1.0 if ok else 0.5 if half else 0.0
    return {"blocked1": score, "blocked2": score, "open1": 0.0 if broke else 1.0}, 100


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        self.t += 1
        return self.t


class GeneTests(unittest.TestCase):
    def test_parse_and_format_roundtrip(self):
        s = "fake:blob=tls_google:repeats=6:tcp_md5:tls_mod=rnd,dupsid"
        self.assertEqual(str(parse_step(s)), s)
        st = parse_step("multisplit:pos=2:seqovl=661:seqovl_pattern=tls_sferum:ip_id=zero")
        self.assertEqual(st.get("pos"), "2")
        self.assertEqual(st.extra, ("ip_id=zero",))  # чужое не теряем
        self.assertIsNone(parse_step("tls_client_hello_clone:blob=x"))

    def test_random_and_mutated_genomes_valid(self):
        rng = random.Random(1)
        for _ in range(300):
            g = evolve.random_genome(rng)
            self.assertTrue(evolve.valid(g))
            m = evolve.mutate(g, rng)
            self.assertTrue(evolve.valid(m))
            self.assertTrue(evolve.valid(evolve.crossover(g, m, rng)))
            # разрезатель — только последним, фейков не больше двух
            self.assertLessEqual(sum(s.func == "fake" for s in m), evolve.MAX_FAKES)

    def test_seqovl_pattern_needs_seqovl(self):
        st = Step("multisplit").with_gene("seqovl_pattern", "tls_google")
        self.assertEqual(st.get("seqovl_pattern"), "")


class EngineTests(unittest.TestCase):
    def run_evolve(self, **kw):
        job = Job("evolve")
        args = dict(evaluate=toy_dpi, baseline=dict(BASELINE), seeds={}, deadline=1e12, rng=random.Random(7),
                    now=Clock(), sleep=lambda s: None, max_evals=600)
        args.update(kw)
        return job, evolve.evolve(job, **args)

    def test_finds_hidden_strategy(self):
        job, res = self.run_evolve()
        best = res["best"][0]
        self.assertEqual((best["fixed"], best["broke"]), (2, 0), best)
        self.assertGreaterEqual(best["evals"], evolve.RETESTS)  # победитель перепроверен
        self.assertIn("midsld", best["key"])
        self.assertIn("tcp_md5", best["key"])
        self.assertEqual(res["phase"], "done")
        self.assertEqual(res["blocked"], ["blocked1", "blocked2"])

    def test_seed_is_used(self):
        seed = (parse_step("fake:blob=tls_google:tcp_md5"), parse_step("multidisorder:pos=midsld"))
        job, res = self.run_evolve(seeds={"general (X)": seed}, max_evals=40)
        self.assertEqual(res["best"][0]["origin"], "general (X)")

    def test_breaking_open_site_loses(self):
        good = (parse_step("fake:blob=tls_google:tcp_md5"), parse_step("multidisorder:pos=midsld"))
        breaking = (parse_step("fake:blob=tls_google"), parse_step("fake:blob=tls_google:tcp_md5"),
                    parse_step("multidisorder:pos=midsld"))
        job, res = self.run_evolve(seeds={"a": breaking, "b": good}, max_evals=20)
        self.assertEqual(res["best"][0]["origin"], "b")

    def test_invalid_args_do_not_win(self):
        job, res = self.run_evolve(evaluate=lambda g: None, max_evals=30)
        self.assertEqual(res["best"], [])

    def test_network_down_waits_instead_of_zeroing(self):
        down = {"n": 0}

        def flaky(g):
            down["n"] += 1
            if 10 <= down["n"] < 14:
                return {t: 0.0 for t in TARGETS}, 100  # интернет пропал
            return toy_dpi(g)
        waits = {"n": 0}

        def net_ok():  # сеть «возвращается» на третьей проверке, пока движок ждёт
            if not 10 <= down["n"] < 14:
                return True
            waits["n"] += 1
            if waits["n"] >= 3:
                down["n"] = 14
            return False
        job, res = self.run_evolve(evaluate=flaky, net_ok=net_ok, max_evals=200)
        self.assertGreaterEqual(waits["n"], 3)
        self.assertTrue(any("пропал интернет" in l["text"] for l in job.log))
        self.assertEqual(res["best"][0]["broke"], 0)

    def test_cancel_and_resume(self):
        saved = {}
        job = Job("evolve")
        kw = dict(evaluate=toy_dpi, baseline=dict(BASELINE), seeds={}, deadline=1e12, now=Clock(),
                  sleep=lambda s: None, save=saved.update)
        evolve.evolve(job, rng=random.Random(3), max_evals=50, **kw)
        n = len(saved["pool"])
        gen = saved["generation"]
        job2 = Job("evolve")
        res = evolve.evolve(job2, rng=random.Random(4), max_evals=100, state=dict(saved), stop_when_ideal=False, **kw)
        self.assertGreater(res["evaluated"], n)
        self.assertGreater(res["generation"], gen)
        self.assertTrue(any("Продолжаю" in l["text"] for l in job2.log))
        self.assertEqual(res["best"][0]["fixed"], 2)

    def test_deadline_stops(self):
        clock = Clock()
        job, res = self.run_evolve(deadline=clock.t + 30, now=clock, max_evals=None)
        self.assertLess(res["evaluated"], 40)


class BatTests(Zapret2Case):
    def test_seeds_from_bundle(self):
        seeds = evolve.seeds_from(self.z2)  # BAT2: fake:blob=tls_google:repeats=6 → multisplit:pos=2
        self.assertEqual([evolve.key(g) for g in seeds.values()], ["fake:blob=tls_google:repeats=6 → multisplit:pos=2"])

    def test_saved_bat_is_a_working_strategy(self):
        steps = ["fake:blob=tls_google:repeats=6:tcp_md5", "multidisorder:pos=midsld"]
        name = evolve.save_bat(self.z2, steps)
        self.assertEqual(name, "general (PIPO EVO 1)")
        self.assertEqual(evolve.save_bat(self.z2, steps), name)  # та же цепочка — тот же файл
        self.assertEqual(evolve.save_bat(self.z2, ["multisplit:pos=2"]), "general (PIPO EVO 2)")
        self.assertIn(b"\r\n", (self.z2 / f"{name}.bat").read_bytes())  # CRLF, как у .bat сборки
        args = zapret.build_args(self.z2, name, zapret.GameFilter())
        self.assertEqual(evolve.tls_chain(args), steps)  # в профиле доменов — ровно найденное
        self.assertIn(f"--lua-init=@{self.z2}\\lua\\blobs.lua", args)
        self.assertEqual(args.count("--lua-desync=multidisorder:pos=midsld"), 3)  # youtube, домены, ipset

    def test_unsafe_step_refused(self):
        for bad in ["fake:blob=x&calc", 'fake:blob="x"', "fake:blob=%PATH%", "send:x"]:
            with self.assertRaises(Exception):
                evolve.save_bat(self.z2, [bad])
        self.assertFalse(list(Path(self.z2).glob("*PIPO*")))

    def test_probe_args_only_tls(self):
        args = evolve.probe_args(self.z2, (parse_step("multisplit:pos=2"),))
        self.assertEqual(args[0], "--chdir")
        self.assertIn("--wf-tcp-out=443", args)
        self.assertEqual(args[-1], "--lua-desync=multisplit:pos=2")


class ShareTests(Zapret2Case):
    STEPS = ["fake:blob=tls_google:repeats=6:tcp_md5", "multisplit:pos=midsld"]

    def test_code_roundtrip(self):
        code = evolve.share_code(self.STEPS, "чинит 6 из 6\n#Ростелеком")
        self.assertTrue(code.startswith("pipo:v1:"))
        sh = evolve.parse_code(code)
        self.assertEqual((sh.steps, sh.note, sh.domains), (self.STEPS, "чинит 6 из 6 Ростелеком", []))

    def test_code_carries_custom_domains(self):
        code = evolve.share_code(self.STEPS, "ноутбук", ["x.com", "instagram.com"])
        self.assertEqual(evolve.parse_code(code).domains, ["x.com", "instagram.com"])
        with self.assertRaises(evolve.EvolveError):
            evolve.parse_code(evolve.CODE_PREFIX + "multisplit:pos=2;d=1.2.3.4")
        targets = [{"group": "Свои", "url": "https://x.com/home"}, {"group": "YouTube", "url": "https://youtube.com"}]
        self.assertEqual(evolve.custom_domains(targets), ["x.com"])

    def test_plain_chain_accepted(self):
        sh = evolve.parse_code("fake:blob=tls_google:repeats=6:tcp_md5 → multisplit:pos=midsld")
        self.assertEqual(sh.steps, self.STEPS)

    def test_bad_codes_refused(self):
        for bad in ["pipo:v1:fake:blob=x&calc.exe", "pipo:v1:send:x", "pipo:v1:", 'pipo:v1:fake:blob="a b"',
                    "pipo:v1:multisplit:pos=2|fake:blob=tls_google",  # фейк после разрезателя
                    "pipo:v1:fake:blob=a|fake:blob=b|fake:blob=c"]:
            with self.assertRaises(evolve.EvolveError, msg=bad):
                evolve.parse_code(bad)

    def test_imports_stored_without_duplicates(self):
        code = evolve.share_code(self.STEPS, "от Пети")
        evolve.add_import(code)
        evolve.add_import(code)
        self.assertEqual([i["steps"] for i in evolve.load_imports()], [self.STEPS])
        evolve.clear_imports()
        self.assertEqual(evolve.load_imports(), [])

    def test_found_strategy_has_share_code(self):
        job = Job("evolve")
        res = evolve.evolve(job, evaluate=toy_dpi, baseline=dict(BASELINE), seeds={}, deadline=1e12,
                            rng=random.Random(7), now=Clock(), sleep=lambda s: None, max_evals=30)
        code = res["best"][0]["code"]
        self.assertEqual(evolve.parse_code(code).steps, res["best"][0]["steps"])
