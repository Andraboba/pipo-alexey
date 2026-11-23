"""Диагностика DNS на поддельной сети: что считается подменой, заглушкой и перехватом."""
from __future__ import annotations

import struct
import unittest

from app import dnscheck
from app.dnscheck import Answer, Transport

REAL = {"rutor.info": ["193.46.255.29"], "flibusta.is": ["179.43.150.83"], "rezka.ag": ["179.43.189.162"],
        "clubtone.do.am": ["185.86.95.62"], "vk.ru": ["87.240.132.72"], "gosuslugi.ru": ["213.59.253.7"],
        "cdn.example": ["104.21.30.148"]}
STUB = "195.208.1.1"
# у каждого сервера по умолчанию своя сеть ответа — перехвата нет
EGRESS_NET = {s.addr: i for i, s in enumerate(dnscheck.UDP_SERVERS)}


def net(system=None, udp=None, whoami=None, doh=None):
    """Поддельная сеть. Каждый параметр — функция(сервер, домен) -> Answer или None (тогда честный ответ)."""
    honest = lambda d: Answer(ips=REAL.get(d, []), rcode=0 if d in REAL else 3, ms=10)

    def pick(fn, *a):
        r = fn(*a) if fn else None
        return r if r is not None else honest(a[-1])

    def udp_fn(server, d):
        if d == dnscheck.WHOAMI:
            return Answer(ips=[(whoami or {}).get(server, f"198.51.{EGRESS_NET[server]}.1")], rcode=0)
        return pick(udp, server, d)

    return Transport(udp=udp_fn, doh=lambda u, d: pick(doh, u, d), dot=lambda h, d: pick(None, h, d),
                     system=lambda d: pick(system and (lambda dd: system(dd)), d))


class DnsCheckTests(unittest.TestCase):
    def test_clean(self):
        r = dnscheck.run(transport=net())
        self.assertEqual(r["verdict"], "clean")
        self.assertEqual(r["stubs"], [])
        self.assertTrue(all(row["alive"] for row in r["udp"]))

    def test_system_stub_detected(self):
        bad = lambda d: Answer(ips=[STUB], rcode=0) if d in dnscheck.BLOCKED_DOMAINS else None
        r = dnscheck.run(transport=net(system=bad))
        self.assertEqual(r["verdict"], "system")
        self.assertEqual(r["stubs"], [STUB])
        self.assertEqual(set(r["system"]["substituted"]), set(dnscheck.BLOCKED_DOMAINS))
        self.assertEqual(r["system"]["domains"]["rutor.info"]["verdict"], "stub")

    def test_cdn_address_is_not_substitution(self):
        # другой адрес у одного домена (CDN, геобалансировка) — «отличается», но не подмена
        other = lambda d: Answer(ips=["104.21.99.99"], rcode=0) if d == "cdn.example" else None
        r = dnscheck.run(["cdn.example"], transport=net(system=other))
        self.assertEqual(r["verdict"], "clean")
        self.assertEqual(r["system"]["differs"], ["cdn.example"])
        self.assertEqual(r["system"]["substituted"], [])

    def test_nxdomain_and_silence_on_blocked(self):
        def udp(server, d):
            if server == "8.8.8.8" and d == "rutor.info":
                return Answer(rcode=3)
            if server == "8.8.8.8" and d == "flibusta.is":
                return Answer(error="нет ответа")  # сервер жив, а на запрещённое молчит
        r = dnscheck.run(transport=net(udp=udp))
        google = next(x for x in r["udp"] if x["addr"] == "8.8.8.8")
        self.assertEqual(google["substituted"], ["rutor.info", "flibusta.is"])
        self.assertEqual(r["verdict"], "udp")
        self.assertEqual(r["foreign_substituted"], ["Google"])

    def test_russian_resolver_blocking_is_expected(self):
        udp = lambda s, d: Answer(rcode=3) if s == "62.76.62.76" and d in dnscheck.BLOCKED_DOMAINS else None
        r = dnscheck.run(transport=net(udp=udp))
        self.assertEqual(r["verdict"], "clean")  # MSK-IX по закону обязан — это не провайдер портит
        self.assertTrue(next(x for x in r["udp"] if x["name"] == "MSK-IX")["substituted"])

    def test_hijack_by_shared_egress(self):
        who = {"8.8.8.8": "10.1.1.5", "1.1.1.1": "10.1.1.7"}  # частный адрес — не в счёт
        r = dnscheck.run(transport=net(whoami=who))
        self.assertEqual(r["hijack"], [])
        who = {"8.8.8.8": "91.100.1.5", "1.1.1.1": "91.100.1.7", "9.9.9.9": "91.100.1.9"}
        r = dnscheck.run(transport=net(whoami=who))
        self.assertEqual(r["hijack"], [{"net": "91.100.1.0/24", "names": ["Cloudflare", "Google", "Quad9"]}])
        self.assertTrue(next(x for x in r["udp"] if x["addr"] == "8.8.8.8")["hijacked"])
        self.assertEqual(r["verdict"], "udp")

    def test_same_operator_is_not_hijack(self):
        who = {"62.76.62.76": "193.232.93.61", "195.208.4.1": "193.232.93.52"}  # MSK-IX и НСДИ — одна организация
        self.assertEqual(dnscheck.run(transport=net(whoami=who))["hijack"], [])

    def test_rewriting_doh_not_in_truth(self):
        # Comss.one отдаёт свой прокси — это не «правда» и не подмена
        doh = lambda u, d: Answer(ips=["83.220.169.155"], rcode=0) if "comss" in u and d == "rutor.info" else None
        r = dnscheck.run(transport=net(doh=doh))
        self.assertNotIn("83.220.169.155", r["truth"]["rutor.info"])
        comss = next(x for x in r["encrypted"] if x["kind"] == "doh" and "comss" in x["addr"])
        self.assertEqual(comss["substituted"], [])
        self.assertIn("Comss.one", [w["name"] for w in r["working_encrypted"]])

    def test_dead_doh_not_recommended(self):
        doh = lambda u, d: Answer(error="нет ответа") if "dns.google" in u else None
        r = dnscheck.run(transport=net(doh=doh))
        names = [(w["kind"], w["name"]) for w in r["working_encrypted"]]
        self.assertNotIn(("doh", "Google"), names)
        self.assertIn(("dot", "Google"), names)

    def test_wire_format_roundtrip(self):
        q = dnscheck.build_query("rutor.info", qid=7)
        # ответ: тот же вопрос + A-запись через указатель на имя
        ans = struct.pack(">HHHHHH", 7, 0x8180, 1, 1, 0, 0) + q[12:] + \
            b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes([193, 46, 255, 29])
        self.assertEqual(dnscheck.parse_answer(ans), (0, ["193.46.255.29"]))
        with self.assertRaises(ValueError):
            dnscheck.parse_answer(b"\0\0")

    def test_offline_is_not_clean(self):
        dead = lambda *a: Answer(error="нет ответа")
        t = Transport(udp=dead, doh=dead, dot=dead, system=dead)
        self.assertEqual(dnscheck.run(transport=t)["verdict"], "offline")

    def test_vpn_fakeip_is_not_isp_substitution(self):
        fake = lambda d: Answer(ips=["198.18.0.7"], rcode=0)
        r = dnscheck.run(transport=net(system=fake))
        self.assertEqual(r["verdict"], "fakeip")
        self.assertEqual(r["system"]["substituted"], [])
