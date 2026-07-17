"""
Specialty resolution — deterministic fuzzy match against `taxonomy_reference`,
no LLM call (design.md §4: "stays a traceable, testable, human-authored tool").
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

# Small curated synonym table (design.md §4) for lay terms that share no text overlap
# with their NUCC classification — pure fuzzy matching alone would miss these.
SYNONYMS: dict[str, str] = {
    "heart doctor": "Cardiovascular Disease",
    "skin doctor": "Dermatology",
    "eye doctor": "Ophthalmology",
    "foot doctor": "Podiatrist",
    "baby doctor": "Pediatrics",
    "brain doctor": "Neurology",
    "bone doctor": "Orthopaedic Surgery",
    "kidney doctor": "Nephrology",
    "lung doctor": "Pulmonary Disease",
    "cancer doctor": "Hematology & Oncology",
    "hormone doctor": "Endocrinology, Diabetes & Metabolism",
}

# Below this rapidfuzz score (0-100), a candidate isn't offered at all.
_MIN_SCORE = 55.0
# If the top two candidates' scores are within this margin, treat the query as ambiguous.
_AMBIGUITY_MARGIN = 8.0
# How many candidates to return when ambiguous or ok.
_MAX_CANDIDATES = 5


@dataclass(frozen=True)
class TaxonomyRow:
    code: str
    grouping: str
    classification: str
    specialization: str | None
    definition: str | None
    nucc_version: str


@dataclass(frozen=True)
class TaxonomyCandidate:
    row: TaxonomyRow
    score: float  # 0.0-1.0


@dataclass(frozen=True)
class ResolveResult:
    status: str  # "ok" | "ambiguous" | "no_match"
    candidates: list[TaxonomyCandidate]


def _corpus_text(row: TaxonomyRow) -> str:
    return f"{row.classification} {row.specialization or ''}".strip()


def resolve(query: str, taxonomy_rows: list[TaxonomyRow]) -> ResolveResult:
    normalized = query.strip().lower()
    search_terms = [normalized]
    synonym_target = SYNONYMS.get(normalized)
    if synonym_target is not None:
        search_terms.append(synonym_target.lower())

    best_score: dict[str, float] = {}
    for row in taxonomy_rows:
        corpus = _corpus_text(row).lower()
        score = max(fuzz.WRatio(term, corpus) for term in search_terms)
        if score > best_score.get(row.code, -1.0):
            best_score[row.code] = score

    ranked = sorted(
        ((code, score) for code, score in best_score.items() if score >= _MIN_SCORE),
        key=lambda item: item[1],
        reverse=True,
    )[:_MAX_CANDIDATES]

    if not ranked:
        return ResolveResult(status="no_match", candidates=[])

    rows_by_code = {row.code: row for row in taxonomy_rows}
    candidates = [
        TaxonomyCandidate(row=rows_by_code[code], score=round(score / 100.0, 4))
        for code, score in ranked
    ]

    if len(candidates) >= 2 and (ranked[0][1] - ranked[1][1]) < _AMBIGUITY_MARGIN:
        return ResolveResult(status="ambiguous", candidates=candidates)

    return ResolveResult(status="ok", candidates=candidates[:1])
