"""Pure-logic tests — no DB needed."""

from provider_registry.taxonomy import TaxonomyRow, resolve

ENDO = TaxonomyRow(
    code="207RE0101X", grouping="Allopathic & Osteopathic Physicians",
    classification="Endocrinology, Diabetes & Metabolism", specialization=None,
    definition="Endocrinology specialist", nucc_version="24.1",
)
CARDIO = TaxonomyRow(
    code="207RC0000X", grouping="Allopathic & Osteopathic Physicians",
    classification="Cardiovascular Disease", specialization=None,
    definition="Cardiology specialist", nucc_version="24.1",
)
DERM = TaxonomyRow(
    code="207N00000X", grouping="Allopathic & Osteopathic Physicians",
    classification="Dermatology", specialization=None,
    definition="Skin specialist", nucc_version="24.1",
)

ROWS = [ENDO, CARDIO, DERM]


def test_direct_text_match_resolves_ok():
    result = resolve("endocrinologist", ROWS)
    assert result.status == "ok"
    assert result.candidates[0].row.code == "207RE0101X"
    assert 0.0 < result.candidates[0].score <= 1.0


def test_synonym_resolves_lay_term_with_no_text_overlap():
    result = resolve("heart doctor", ROWS)
    assert result.status == "ok"
    assert result.candidates[0].row.code == "207RC0000X"


def test_synonym_skin_doctor_resolves_dermatology():
    result = resolve("skin doctor", ROWS)
    assert result.status == "ok"
    assert result.candidates[0].row.code == "207N00000X"


def test_nonsense_query_is_no_match():
    result = resolve("xyzzy plugh quux", ROWS)
    assert result.status == "no_match"
    assert result.candidates == []


def test_result_never_fabricates_a_code_not_in_the_input_rows():
    result = resolve("endocrinologist", ROWS)
    valid_codes = {row.code for row in ROWS}
    assert all(c.row.code in valid_codes for c in result.candidates)
