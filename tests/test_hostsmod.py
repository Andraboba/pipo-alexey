from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import hostsmod

SAMPLE = """### example: hosts file
# Последнее обновление: 14 ноября 2026
# Эти IP-адреса принадлежат DNS:
# 159.194.200.33

# ChatGPT (OpenAI) AI
217.60.179.6 chatgpt.com
217.60.179.6 auth.openai.com
# Claude AI
193.233.112.67 claude.ai
193.233.112.67 api.anthropic.com
# Google Gemini AI
159.194.200.33 gemini.google.com
159.194.200.33 api.claude.ai
# Блокировка
0.0.0.0 ad.mail.ru
127.0.0.1 localhost
"""


class ParseTests(unittest.TestCase):
    def test_claude_never_parsed(self):
        dropped = []
        secs = hostsmod.parse(SAMPLE, dropped)
        self.assertEqual([s.name for s in secs], ["ChatGPT (OpenAI) AI", "Google Gemini AI"])
        domains = [d for s in secs for _, d in s.entries]
        self.assertEqual(domains, ["chatgpt.com", "auth.openai.com", "gemini.google.com"])  # api.claude.ai из чужой секции тоже выкинут
        reasons = {d["line"]: d["reason"] for d in dropped}
        self.assertEqual(reasons["193.233.112.67 claude.ai"], "секция Claude/Anthropic")
        self.assertEqual(reasons["159.194.200.33 api.claude.ai"], "домен Claude/Anthropic")
        self.assertIn("блокировка", reasons["0.0.0.0 ad.mail.ru"])
        self.assertTrue(all(s.ai for s in secs))

    def test_excluded(self):
        for d in ("claude.ai", "www.claude.com", "statsig.anthropic.com", "claudeusercontent.com", "x.claudemcpclient.com"):
            self.assertTrue(hostsmod.excluded(d), d)
        for d in ("chatgpt.com", "gemini.google.com", "grok.com"):
            self.assertFalse(hostsmod.excluded(d), d)


class HostsFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pipo-hosts-"))
        self.hosts = self.tmp / "hosts"
        self.hosts.write_bytes(b"# user hosts\r\n127.0.0.1 my.local\r\n")
        self.patches = [
            mock.patch.object(hostsmod, "HOSTS", self.hosts),
            mock.patch.object(hostsmod, "DATA_DIR", self.tmp / "data"),
            mock.patch.object(hostsmod.winutil, "run"),
        ]
        for p in self.patches:
            p.start()
        hostsmod.write_text_atomic(hostsmod._cache("geohide"), SAMPLE + "\n# A\n1.2.3.4 a.example\n# B\n1.2.3.5 b.example\n")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_apply_and_remove_keep_user_lines(self):
        hostsmod.apply("geohide", ["ChatGPT (OpenAI) AI", "Claude AI", "Google Gemini AI"])
        text = self.hosts.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1 my.local", text)
        self.assertIn("217.60.179.6 chatgpt.com", text)
        self.assertNotIn("claude", text.lower())
        self.assertNotIn("anthropic", text.lower())
        self.assertEqual(hostsmod.status()["in_hosts"], 3)
        self.assertEqual((self.tmp / "data" / "backups" / "hosts.original").read_bytes(), b"# user hosts\r\n127.0.0.1 my.local\r\n")

        hostsmod.apply("geohide", ["A"])  # повторное применение заменяет блок, а не дописывает
        text = self.hosts.read_text(encoding="utf-8")
        self.assertEqual(text.count(hostsmod.BEGIN), 1)
        self.assertNotIn("chatgpt.com", text)

        hostsmod.remove()
        self.assertEqual(self.hosts.read_bytes(), b"# user hosts\r\n127.0.0.1 my.local\r\n")  # байт в байт как было

    def test_reverted_detected(self):
        hostsmod.apply("geohide", ["A"])
        self.hosts.write_bytes(b"# user hosts\r\n")  # Защитник откатил
        self.assertTrue(hostsmod.status()["reverted"])


if __name__ == "__main__":
    unittest.main()
