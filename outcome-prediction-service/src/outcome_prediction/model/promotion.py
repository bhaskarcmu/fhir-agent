"""Promotion records (O33, design.md §8): the service serves only a promoted artifact.

`PROMOTION.json` sits beside an artifact's manifest — written after it, so not listed in it — and
records the manifest's checksums, binding the record to exactly those files. It names the
decision that approved serving, and where the model was confirmed:

    {"decision": "O59", "contract_version": "meps-portable-v2", "label": "admit_nonobstetric_y2",
     "round": "003-portable-contract", "run": "nonobstetric-v2", "promoted_at": "...",
     "files": {"model.joblib": "<sha256>", "comparison.joblib": "...", "metadata.json": "..."}, ...}

    python -m outcome_prediction.model.promotion retrofit models/gbm-meps25-v1-<id> --decision O2
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from outcome_prediction.model.artifact import COMPARISON, MANIFEST, METADATA, MODEL, PROMOTION, verify_artifact

DECISION = re.compile(r"^O\d+$")


class PromotionRefused(RuntimeError):
    """The artifact has no valid promotion record; the service must not serve it."""


def _manifest(directory: Path) -> dict[str, str]:
    return {name: digest for digest, _, name in
            (line.partition("  ") for line in (directory / MANIFEST).read_text().splitlines())}


def write_promotion(directory: Path, decision: str, **record) -> Path:
    """Record a promotion of a verified artifact. Never overwrites an existing record."""
    if not DECISION.match(decision):
        raise PromotionRefused(f"decision must look like O59, not {decision!r}")
    verify_artifact(directory)
    path = directory / PROMOTION
    if path.exists():
        raise PromotionRefused(f"{path} exists — a promotion is recorded once")
    metadata = json.loads((directory / METADATA).read_text())
    doc = {"decision": decision, "contract_version": metadata["contract_version"],
           "label": metadata.get("label"), "model_id": metadata["model_id"],
           "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           **record, "files": _manifest(directory)}
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def verify_promotion(directory: Path) -> dict:
    """The artifact's promotion record, if it is valid for exactly these files; else refused."""
    path = directory / PROMOTION
    if not path.exists():
        raise PromotionRefused(f"{directory.name}: not promoted — no {PROMOTION} (decisions.md O33)")
    doc = json.loads(path.read_text())
    if not DECISION.match(str(doc.get("decision", ""))):
        raise PromotionRefused(f"{directory.name}: {PROMOTION} names no decision")
    if doc.get("files") != _manifest(directory):
        raise PromotionRefused(f"{directory.name}: {PROMOTION} was made for different files")
    metadata = json.loads((directory / METADATA).read_text())
    if doc.get("contract_version") != metadata.get("contract_version"):
        raise PromotionRefused(f"{directory.name}: {PROMOTION} is for contract {doc.get('contract_version')}")
    if not {MODEL, COMPARISON, METADATA} <= set(doc["files"]):
        raise PromotionRefused(f"{directory.name}: {PROMOTION} doesn't cover the model files")
    return doc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("retrofit", help="record the promotion of an artifact approved by a decision")
    r.add_argument("artifact", type=Path)
    r.add_argument("--decision", required=True)
    r.add_argument("--note", default="")
    args = parser.parse_args(argv)
    print(write_promotion(args.artifact, args.decision, note=args.note or None))


if __name__ == "__main__":
    main()
