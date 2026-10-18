"""The holdout ledger (decisions.md O32): every look at the test panels is logged BEFORE it
happens, and test-panel scoring refuses to run for a candidate that has no entry.

The ledger is a committed, append-only Markdown table: outcome-prediction-lab/holdout-ledger.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[2] / "holdout-ledger.md"
HEADER = """# Holdout ledger — every look at the test panels

Append-only (docs/phase8/experimentation-protocol.md §5). A row is written BEFORE the test
panels are scored; `holdout.require` refuses to score a candidate without one.

| When (UTC) | Round | Candidate | Test panels | Why this look |
|---|---|---|---|---|
"""


class NotInLedger(PermissionError):
    """Test-panel scoring was attempted for a candidate with no ledger entry."""


def _rows(ledger: Path) -> list[list[str]]:
    if not ledger.exists():
        return []
    return [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in ledger.read_text().splitlines()
            if line.startswith("| 20")]


def record(round_id: str, candidate: str, why: str, test_panels=(26, 27), ledger: Path = LEDGER) -> None:
    if "|" in candidate + why + round_id:
        raise ValueError("ledger fields can't contain '|'")
    if not ledger.exists():
        ledger.write_text(HEADER)
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    panels = ", ".join(map(str, test_panels))
    with ledger.open("a") as f:
        f.write(f"| {when} | {round_id} | {candidate} | {panels} | {why} |\n")


def require(round_id: str, candidate: str, ledger: Path = LEDGER) -> None:
    if not any(r[1] == round_id and r[2] == candidate for r in _rows(ledger)):
        raise NotInLedger(f"no holdout-ledger entry for {round_id} / {candidate} — record the look "
                          f"first (holdout.record), then score the test panels")
