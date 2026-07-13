"""Real-time redaction of structured secrets.

Applied to every string that will be committed (prompts, responses, tool
summaries, raw copies, index). Redact-and-continue: matches are masked and
processing never stops, so archiving cannot stall or lose turns. This catches
structured tokens only, not free-form PHI/business secrets in prose.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MASK = "‹redacted:{category}›"  # ‹redacted:CATEGORY›


@dataclass
class Pattern:
    category: str
    regex: re.Pattern
    repl: Callable[[re.Match], str]


def _full(category: str) -> Callable[[re.Match], str]:
    return lambda m: MASK.format(category=category)


def _keep_prefix(category: str, group: int) -> Callable[[re.Match], str]:
    """Preserve a leading group (e.g. the env-var name or URL scheme)."""
    return lambda m: m.group(group) + MASK.format(category=category)


def _builtin_patterns() -> list[Pattern]:
    def p(category, regex, repl=None, flags=0):
        return Pattern(category, re.compile(regex, flags), repl or _full(category))

    return [
        # Private key blocks first (multiline, greedy-ish but bounded).
        p("private-key",
          r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
          flags=re.DOTALL),
        p("anthropic-key", r"sk-ant-[A-Za-z0-9\-_]{12,}"),
        p("github-token", r"gh[posru]_[A-Za-z0-9]{20,}"),
        p("github-token", r"github_pat_[A-Za-z0-9_]{20,}"),
        p("openai-key", r"sk-[A-Za-z0-9]{20,}"),
        p("aws-access-key", r"AKIA[0-9A-Z]{16}"),
        p("bearer-token",
          r"(Authorization:\s*Bearer\s+)[A-Za-z0-9\-._~+/]+=*",
          _keep_prefix("bearer-token", 1), re.IGNORECASE),
        p("url-credentials",
          r"([a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]+:)[^\s:/@]+@",
          _keep_prefix("url-credentials", 1)),
        p("env-secret",
          r"(?im)^(\s*[A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Za-z0-9_]*\s*=\s*)\S+",
          _keep_prefix("env-secret", 1)),
    ]


class Redactor:
    def __init__(self, extra_patterns: list[Pattern] | None = None):
        self.patterns = _builtin_patterns() + (extra_patterns or [])
        self.counts: Counter = Counter()

    @classmethod
    def from_file(cls, patterns_file: Path | None) -> "Redactor":
        extra: list[Pattern] = []
        if patterns_file and patterns_file.exists():
            for line in patterns_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        extra.append(Pattern("custom", re.compile(line), _full("custom")))
                    except re.error:
                        continue
        return cls(extra)

    def redact(self, text: str) -> str:
        if not text:
            return text
        for pat in self.patterns:
            def _sub(m, _pat=pat):
                self.counts[_pat.category] += 1
                return _pat.repl(m)
            text = pat.regex.sub(_sub, text)
        return text
