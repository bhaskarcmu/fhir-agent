"""DB-backed tests against the fixture in fixtures.sql — see conftest.py for the
self-skip-when-unreachable behavior."""

from provider_registry.location import Coordinate, HaversineSqlLocationSearch, resolve_zip_to_coordinate

CHAPEL_HILL = Coordinate(lat=35.9132, lon=-79.0558)
ENDO_CODE = "207RE0101X"
CARDIO_CODE = "207RC0000X"


def test_results_ordered_by_distance_ascending(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    # Chapel Hill -> Raleigh is ~25.1mi straight-line; use 30mi so John Smith is
    # reliably included without the test riding the radius boundary.
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=30, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=None,
    )
    npis = [r["npi"] for r in results]
    assert npis[0] == "1111111111"  # Jane Doe, at the origin — nearest
    assert "2222222222" in npis      # John Smith, Raleigh — farther but within 30mi
    distances = [r["distance_miles"] for r in results]
    assert distances == sorted(distances)


def test_deactivated_provider_excluded_by_default(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=None,
    )
    npis = {r["npi"] for r in results}
    assert "3333333333" not in npis  # deactivated — must never surface in default search


def test_deactivated_provider_included_when_explicitly_requested(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=None, include_deactivated=True,
    )
    npis = {r["npi"] for r in results}
    assert "3333333333" in npis


def test_entity_type_filter_excludes_organizations(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=None, entity_type="individual",
    )
    assert all(r["entity_type"] == 1 for r in results)
    assert "4444444444" not in {r["npi"] for r in results}  # Duke Health org


def test_entity_type_filter_organization_only(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=None, entity_type="organization",
    )
    assert {r["npi"] for r in results} == {"4444444444"}


def test_taxonomy_filter_excludes_non_matching_specialty(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=None,
    )
    assert "5555555555" not in {r["npi"] for r in results}  # cardiologist, wrong taxonomy


def test_far_away_provider_excluded_by_tight_radius_but_found_by_wide_radius(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    tight = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[CARDIO_CODE],
        limit=10, accepting_new_patients=None,
    )
    assert tight == []  # LA cardiologist is genuinely ~2400mi from Chapel Hill

    wide = search.search_near(
        origin=CHAPEL_HILL, radius_miles=3000, taxonomy_codes=[CARDIO_CODE],
        limit=10, accepting_new_patients=None,
    )
    assert {r["npi"] for r in wide} == {"5555555555"}


def test_accepting_new_patients_false_returns_nothing(db_pool):
    # No provider ever has a confirmed accepting_new_patients=False this build
    # (design.md P6) -- explicit False can never match anything.
    search = HaversineSqlLocationSearch(db_pool)
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=False,
    )
    assert results == []


def test_every_result_carries_lineage(db_pool):
    search = HaversineSqlLocationSearch(db_pool)
    results = search.search_near(
        origin=CHAPEL_HILL, radius_miles=25, taxonomy_codes=[ENDO_CODE],
        limit=10, accepting_new_patients=None,
    )
    assert results
    for r in results:
        assert r["lineage"]["source"] == "NPPES"
        assert r["lineage"]["ingestion_run_id"] == "11111111-1111-1111-1111-111111111111"


def test_resolve_zip_to_coordinate_known_and_unknown(db_pool):
    coord = resolve_zip_to_coordinate(db_pool, "27514")
    assert coord is not None
    assert coord.lat == 35.9132

    assert resolve_zip_to_coordinate(db_pool, "00000") is None
