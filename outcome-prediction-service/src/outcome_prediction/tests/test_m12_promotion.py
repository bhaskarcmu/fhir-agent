"""M12: promotion records, serving the promoted `meps-portable-v2` model beside `meps25-v1`, and
its rows from records (honest missing values, code features, leakage)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from outcome_prediction import api, contract
from outcome_prediction.etl.canonical import Canonical
from outcome_prediction.etl.extract import synthea_csv
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.model.promotion import PromotionRefused, verify_promotion, write_promotion
from outcome_prediction.scoring import Scorer
from outcome_prediction.tests.synthetic_portable import build_portable_artifact
from outcome_prediction.tests.test_etl_synthea import _future_variants
from outcome_prediction.tests.test_scoring_api import AS_OF, PATIENT, Server

FIXTURE = Path(__file__).parent / "fixtures" / "synthea_csv"


@pytest.fixture(scope="module")
def portable(tmp_path_factory) -> Path:
    return build_portable_artifact(tmp_path_factory.mktemp("m12") / "models")


@pytest.fixture(scope="module")
def canon() -> Canonical:
    return synthea_csv.read(FIXTURE)


# ── promotion records (O33) ──────────────────────────────────────────────────────────

def test_an_unpromoted_artifact_is_refused(portable, tmp_path):
    bare = tmp_path / "bare"
    shutil.copytree(portable, bare)
    (bare / "PROMOTION.json").unlink()
    with pytest.raises(PromotionRefused, match="not promoted"):
        Scorer(bare)


def test_an_unpromoted_artifact_stops_the_service(portable, tmp_path, monkeypatch):
    bare = tmp_path / "bare"
    shutil.copytree(portable, bare)
    (bare / "PROMOTION.json").unlink()
    monkeypatch.setenv("OUTCOME_PREDICTION_ARTIFACTS", str(bare))
    with pytest.raises(PromotionRefused):
        with TestClient(api.app):
            pass


def test_a_record_made_for_other_files_is_refused(portable, tmp_path):
    moved = tmp_path / "moved"
    shutil.copytree(portable, moved)
    record = json.loads((moved / "PROMOTION.json").read_text())
    record["files"]["model.joblib"] = "0" * 64
    (moved / "PROMOTION.json").write_text(json.dumps(record))
    with pytest.raises(PromotionRefused, match="different files"):
        verify_promotion(moved)


def test_a_promotion_is_recorded_once_and_names_a_decision(portable, tmp_path):
    with pytest.raises(PromotionRefused, match="once"):
        write_promotion(portable, "O59")
    fresh = tmp_path / "fresh"
    shutil.copytree(portable, fresh)
    (fresh / "PROMOTION.json").unlink()
    with pytest.raises(PromotionRefused, match="O59"):
        write_promotion(fresh, "approved")
    assert verify_promotion(portable)["decision"] == "O59"


# ── serving meps-portable-v2 ─────────────────────────────────────────────────────────

@pytest.fixture
def client(portable, monkeypatch):
    monkeypatch.setenv("OUTCOME_PREDICTION_ARTIFACTS", str(portable))
    api.app.dependency_overrides[api.get_client] = lambda: Server()
    with TestClient(api.app) as c:
        yield c
    api.app.dependency_overrides.clear()


def test_the_promoted_target_scores_a_patient(client):
    r = client.post("/risk/nonobstetric-admission-12m", json={"patient_id": PATIENT, "as_of": AS_OF})
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["prediction"][0]
    assert p["outcome"]["text"] == "Hospital admission not related to pregnancy or childbirth"
    assert {e["valueString"] for e in p["extension"] if e["url"].endswith("contract-version")} == {"meps-portable-v2"}
    warnings = [e["valueString"] for e in body["extension"]]
    assert to_contract.WARN_NO_INCOME_V2 in warnings
    assert not any("pharmacy claims" in w for w in warnings)          # v2's records tier uses no fills
    reasons = [e["valueString"] for e in p["extension"] if e["url"].endswith("top-reasons")]
    assert "povcaty1" not in reasons and "racethx" not in reasons     # missing input / O50
    assert body["basis"]


def test_a_target_without_a_promoted_model_is_503(client):
    assert client.post("/risk/hospitalization-12m", json={"patient_id": PATIENT}).status_code == 503
    assert client.post("/risk/unknown-12m", json={"patient_id": PATIENT}).status_code == 404


def _v2_row(**overrides) -> dict:
    f = {c: 0.0 for c in contract.names(contract.DEFAULT_TIERS)} | {
        "sex": 2, "racethx": 2, "regiony1": 3, "agey1x": 70, "inscovy1": 2, "povcaty1": None, "n_icd": 4}
    return {"patient_ref": "r1", "features": f | {contract.TEXT_COLUMN: "icdI10 icdE11"} | overrides}


def test_v2_contract_rows(client):
    r = client.post("/risk/nonobstetric-admission-12m/contract-rows",
                    json={"contract_version": "meps-portable-v2", "rows": [_v2_row()]})
    assert r.status_code == 200, r.text
    ra = r.json()["entry"][0]["resource"]
    assert [e["valueString"] for e in ra["extension"]] == [to_contract.WARN_NO_INCOME_V2]


@pytest.mark.parametrize("change, message", [
    ({"agey1x": None}, "required"), ({"sex": 7}, "not one of"), ({"n_icd": -1}, "≥ 0"),
    ({contract.TEXT_COLUMN: 5}, "string of ICD-10 codes"), ({"bmi": 30}, "unknown features"),
])
def test_bad_v2_rows_are_refused(client, change, message):
    r = client.post("/risk/nonobstetric-admission-12m/contract-rows",
                    json={"contract_version": "meps-portable-v2", "rows": [_v2_row(**change)]})
    assert r.status_code == 422 and message in r.text


def test_v2_rows_refuse_the_v1_contract(client):
    r = client.post("/risk/nonobstetric-admission-12m/contract-rows", json={"contract_version": "meps25-v1", "rows": [_v2_row()]})
    assert r.status_code == 422 and "meps-portable-v2" in r.text


# ── v2 rows from records ─────────────────────────────────────────────────────────────

def test_v2_rows_are_honest_about_what_records_lack(canon):
    person = canon.person.assign(income=np.nan, state=["Ontario", *canon.person.state.iloc[1:]])
    rows = to_contract.portable_scoring_rows(Canonical(**{**canon.tables(), "person": person}), pd.Timestamp(AS_OF))
    assert rows.povcaty1.isna().all()                                  # missing, never defaulted (O53)
    assert np.isnan(rows.set_index("patient_ref").loc[person.person_id.iloc[0], "regiony1"])
    assert list(rows.columns) == ["patient_ref", *contract.names(contract.DEFAULT_TIERS), contract.TEXT_COLUMN]


def test_medicare_and_medicaid_come_from_the_payer(canon):
    rows = to_contract.portable_scoring_rows(canon, pd.Timestamp(AS_OF)).set_index("patient_ref")
    cov = canon.coverage
    window = cov[(cov.start < pd.Timestamp("2024-01-01")) & (cov.stop.isna() | (cov.stop >= pd.Timestamp("2023-01-01")))]
    for pid in rows.index:
        payers = set(window[window.person_id == pid].payer.str.lower())
        assert rows.loc[pid, "mcrevy1"] == float(any(p in ("medicare", "dual eligible") for p in payers))
        assert rows.loc[pid, "mcdevy1"] == float(any(p in ("medicaid", "dual eligible") for p in payers))


def test_code_features_use_only_conditions_active_in_the_window(canon):
    pid = canon.person.person_id.iloc[0]
    old = pd.DataFrame([{"person_id": pid, "start": pd.Timestamp("2005-01-01"), "stop": pd.Timestamp("2010-01-01"),
                         "code": "I10", "description": "x", "source_ref": "old"}])
    with_old = Canonical(**{**canon.tables(), "condition": pd.concat([canon.condition, old], ignore_index=True)})
    a = to_contract.portable_scoring_rows(canon, pd.Timestamp(AS_OF)).set_index("patient_ref")
    b = to_contract.portable_scoring_rows(with_old, pd.Timestamp(AS_OF)).set_index("patient_ref")
    assert a.loc[pid, "n_icd"] == b.loc[pid, "n_icd"]                 # resolved long before the window
    assert b.loc[pid, "hibpdx"] == 1                                    # but "ever told" still counts it


@pytest.mark.parametrize("as_of", ["2023-06-30", "2023-12-31"])
def test_records_after_as_of_change_no_v2_input(canon, as_of):
    as_of = pd.Timestamp(as_of)
    base = to_contract.portable_scoring_rows(canon, as_of)
    for name, variant in _future_variants(canon, as_of).items():
        pd.testing.assert_frame_equal(to_contract.portable_scoring_rows(variant, as_of), base, obj=name)
