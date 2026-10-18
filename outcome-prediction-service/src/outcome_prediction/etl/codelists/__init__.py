"""Versioned clinical code lists for the diagnosis flags (M13, FR-T4).

One list per flag (`<flag>.json`): ICD-10-CM prefixes — a 3-character category by default,
longer where a category mixes meanings (I25.2 "old myocardial infarction" sits inside I25 "chronic
ischemic heart disease"). Every list is **unreviewed** until a clinical owner signs off
(decisions.md O27); each says what it includes and what it leaves out, for that review.

Conditions arrive as SNOMED CT (Synthea, most EHRs) or ICD-10-CM. SNOMED codes are mapped with
`maps/snomed_icd10cm.synthea-4.0.0.json`, extracted from the pinned Synthea v4.0.0 release
(Apache-2.0; decision O73); a code already in ICD-10-CM is used as it is.

    python -m outcome_prediction.etl.codelists check       # every list entry exists in ICD-10-CM FY2026
    python -m outcome_prediction.etl.codelists build-map   # re-extract the SNOMED map from the pinned jar
"""
from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
FLAGS = ("hibpdx", "chddx", "angidx", "midx", "ohrtdx", "strkdx", "emphdx", "diabdx", "arthdx", "asthdx", "choldx")
MAP_FILE = HERE / "maps" / "snomed_icd10cm.synthea-4.0.0.json"
SYNTHEA_MAP_MEMBER = "export/condition_code_map.json"

# CDC/NCHS ICD-10-CM FY2026 code descriptions (public domain) — the one pin; the lab imports it.
ICD10CM = {
    "url": "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/ICD10CM/2026/icd10cm-Code%20Descriptions-2026.zip",
    "name": "icd10cm-code-descriptions-2026.zip",
    "sha256": "a852eb91b3344ae38476e63816976ee1eeb94dcced7151118324f060e8499f88",
    "member": "icd10cm-order-2026.txt",
}
ICD10_SHAPE = re.compile(r"^[A-Z][0-9][0-9A-Z](\.?[0-9A-Z]{0,4})?$")


def normalise(code: str) -> str:
    """ICD-10-CM without the dot, upper case: 'i25.2' -> 'I252'."""
    return code.replace(".", "").strip().upper()


def is_icd10(code: str) -> bool:
    return bool(ICD10_SHAPE.match(code.strip().upper()))


@lru_cache(maxsize=1)
def flag_lists() -> dict[str, dict]:
    return {f: json.loads((HERE / f"{f}.json").read_text()) for f in FLAGS}


@lru_cache(maxsize=1)
def prefixes() -> dict[str, tuple[str, ...]]:
    return {f: tuple(normalise(c["prefix"]) for c in doc["codes"]) for f, doc in flag_lists().items()}


@lru_cache(maxsize=1)
def snomed_map() -> dict[str, list[str]]:
    return json.loads(MAP_FILE.read_text())["map"]


def icd10_codes(code: str | None) -> list[str]:
    """ICD-10-CM codes (normalised) for one condition code: itself if it is ICD-10-CM, else its
    SNOMED CT mapping; [] if it can't be mapped."""
    if not code:
        return []
    if is_icd10(code):
        return [normalise(code)]
    return snomed_map().get(code.strip(), [])


def flags_for(codes: list[str]) -> set[str]:
    """The flags any of these (normalised ICD-10-CM) codes sets."""
    return {f for f, ps in prefixes().items() if any(c.startswith(ps) for c in codes)}


# Targets that only apply in a context a condition record doesn't carry: pregnancy (O), the
# perinatal period (P), injury and poisoning (T) — e.g. essential hypertension -> P29.2.
CONTEXT_CHAPTERS = ("O", "P", "T")


def flags_for_code(code: str | None) -> set[str]:
    """The flags ONE condition code sets (decision O73).

    An ICD-10-CM code sets the flags its prefixes match. A SNOMED code is mapped, and Synthea's
    map lists every ICD-10-CM code a concept *may* become — chronic kidney disease -> {CKD due to
    hypertension, CKD due to diabetes, CKD stage 1}. So, after dropping context-only targets:
    a flag is set when MOST targets are in its list, or exactly HALF when no other flag claims any
    target (history of CABG -> Z95.1 / Z95.818 is coronary disease; CKD, split between diabetes
    and hypertension, is neither). "Any target" would call CKD hypertension; "every target" would
    lose diabetic neuropathy, whose map pairs E11.4x with G53.
    """
    if not code:
        return set()
    if is_icd10(code):
        return flags_for([normalise(code)])
    targets = snomed_map().get(code.strip(), [])
    kept = [t for t in targets if not t.startswith(CONTEXT_CHAPTERS)] or targets
    if not kept:
        return set()
    counts = {f: sum(t.startswith(ps) for t in kept) for f, ps in prefixes().items()}
    if majority := {f for f, n in counts.items() if n * 2 > len(kept)}:
        return majority
    half = {f for f, n in counts.items() if n * 2 == len(kept)}
    claimed = {f for f, n in counts.items() if n}
    return half if len(half) == 1 and claimed == half else set()

def icd10_category(code: str | None) -> str | None:
    """The 3-character ICD-10-CM category of one condition code — what MEPS releases, and what
    `meps-portable-v2`'s code features count (M12). ICD-10-CM: its first three characters. SNOMED:
    the category most of its (non-context) targets share; None when they don't agree — chronic
    kidney disease spans E09–E13, I12, I13, N18, and a guess would feed the comorbidity scores."""
    if not code:
        return None
    if is_icd10(code):
        return normalise(code)[:3]
    targets = snomed_map().get(code.strip(), [])
    kept = [t for t in targets if not t.startswith(CONTEXT_CHAPTERS)] or targets
    if not kept:
        return None
    from collections import Counter
    category, n = Counter(t[:3] for t in kept).most_common(1)[0]
    return category if n * 2 > len(kept) else None


def versions() -> dict[str, dict]:
    """What a report or a model card cites: each list's version and review status, and the map."""
    meta = json.loads(MAP_FILE.read_text())["source"]
    return {"lists": {f: {"version": d["version"], "status": d["status"]} for f, d in flag_lists().items()},
            "snomed_map": meta}


# ── maintenance ──────────────────────────────────────────────────────────────────────

def cdc_codes() -> dict[str, str]:
    """Every ICD-10-CM FY2026 code and category (normalised) -> description, from the pinned file."""
    from outcome_prediction.meps.download import obtain_original
    from outcome_prediction.meps.manifest import archive_dir
    data = obtain_original(ICD10CM["name"], ICD10CM["sha256"], ICD10CM["url"], archive_dir() / "reference", mirrors=[])
    lines = zipfile.ZipFile(io.BytesIO(data)).read(ICD10CM["member"]).decode("latin1").splitlines()
    return {ln[6:13].strip(): ln[77:].strip() for ln in lines}


def check(codes: dict[str, str] | None = None) -> list[str]:
    """Problems with the lists: unknown prefixes, descriptions that differ from the release,
    missing review status. Empty means every list is consistent with ICD-10-CM FY2026."""
    codes = codes or cdc_codes()
    problems = []
    for flag, doc in flag_lists().items():
        if doc.get("status") not in ("unreviewed", "reviewed"):
            problems.append(f"{flag}: status must be 'unreviewed' or 'reviewed'")
        for entry in doc["codes"]:
            code = normalise(entry["prefix"])
            if code not in codes:
                problems.append(f"{flag}: {entry['prefix']} is not an ICD-10-CM FY2026 code")
            elif codes[code] != entry["description"]:
                problems.append(f"{flag}: {entry['prefix']} is '{codes[code]}', not '{entry['description']}'")
    return problems


def build_map() -> Path:
    """Re-extract the SNOMED CT -> ICD-10-CM map from the pinned Synthea jar (verified by SHA-256)."""
    from outcome_prediction.etl.synthea import SYNTHEA_SHA256, SYNTHEA_VERSION, ensure_jar
    with zipfile.ZipFile(ensure_jar()) as jar:
        raw = json.loads(jar.read(SYNTHEA_MAP_MEMBER))
    mapping = {snomed: sorted({normalise(t["code"]) for t in targets}) for snomed, targets in sorted(raw.items())}
    MAP_FILE.parent.mkdir(exist_ok=True)
    MAP_FILE.write_text(json.dumps({
        "source": {"synthea": SYNTHEA_VERSION, "jar_sha256": SYNTHEA_SHA256, "member": SYNTHEA_MAP_MEMBER,
                   "licence": "Apache-2.0 (Synthea, The MITRE Corporation)", "codes": len(mapping)},
        "map": mapping}, indent=0, sort_keys=False) + "\n")
    return MAP_FILE


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cmd", choices=["check", "build-map"])
    args = parser.parse_args(argv)
    if args.cmd == "build-map":
        print(build_map())
        return
    problems = check()
    print("\n".join(problems) or f"{len(FLAGS)} lists consistent with ICD-10-CM FY2026 "
                                  f"({sum(len(d['codes']) for d in flag_lists().values())} prefixes)")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
