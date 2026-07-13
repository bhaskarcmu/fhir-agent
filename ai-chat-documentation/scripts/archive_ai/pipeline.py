"""Full-regeneration pipeline: discover -> parse -> redact -> render -> write.

Every run reprocesses all (non-excluded) sessions. This keeps INDEX.md correct
and the whole run idempotent; the publisher's empty-diff check makes redundant
runs free, so no content-hash manifest is needed at this data volume.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import discovery
from .config import SOURCE_NAME, Config
from .parser import parse_session
from .redactor import Redactor
from .renderer import render_index, render_markdown
from .writer import atomic_write


@dataclass
class PipelineResult:
    sessions_processed: int = 0
    sessions_excluded: int = 0
    files_written: int = 0
    redactions: Counter = field(default_factory=Counter)


def run(config: Config) -> PipelineResult:
    sessions = discovery.find_sessions(config)
    exclusions = config.load_exclusions()
    redactor = Redactor.from_file(config.patterns_file)
    result = PipelineResult()

    conversations = []
    for path in sessions:
        if path.stem in exclusions:
            result.sessions_excluded += 1
            continue
        conv = parse_session(path)
        conversations.append(conv)
        result.sessions_processed += 1

        raw_text = path.read_text(encoding="utf-8", errors="replace")
        atomic_write(config.raw_dir / f"{conv.id}.jsonl", redactor.redact(raw_text))
        atomic_write(config.markdown_dir / f"{conv.id}.md", redactor.redact(render_markdown(conv)))
        result.files_written += 2

    markdown_subpath = f"markdown/{SOURCE_NAME}"
    atomic_write(config.index_path, redactor.redact(render_index(conversations, markdown_subpath)))
    result.files_written += 1
    result.redactions = redactor.counts
    return result


def commit_message(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"Archive Claude Code conversations: {now.strftime('%Y-%m-%d %H:%M UTC')}"
