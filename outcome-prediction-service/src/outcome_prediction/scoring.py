"""Scoring contract rows with a verified artifact: probability, comparison score, percentile and
per-patient reasons (FR-S2, FR-M8).

Reasons are found by **occlusion**: re-score the patient with one input at a time set to what a
typical MEPS adult has (`etl/meps_reference.json` → `typical`). An input whose typical value would
lower the estimate is a reason the estimate is higher. It is deterministic, needs no extra
library, and costs one batched prediction per request. Like every explanation, it describes what
the model weighed, not what causes admissions. Inputs that were defaulted or are missing (e.g.
income not recorded) and race/ethnicity (O50) are never given as reasons.

Two contracts are served (M12): `meps25-v1` (the reproduced prototype) and `meps-portable-v2`
(the promoted production contract, O59). Either way an artifact is served only if it is promoted
(PROMOTION.json, O33).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from outcome_prediction import contract as portable
from outcome_prediction.model import CONTRACT_VERSION, FEATURES, comparison_matrix, feature_matrix
from outcome_prediction.model.artifact import Artifact, load_artifact, risk_percentile
from outcome_prediction.model.promotion import verify_promotion
from outcome_prediction.settings import models_dir

REFERENCE = Path(__file__).parent / "etl" / "meps_reference.json"
TOP_REASONS = 3
# Never given as a per-patient reason, though the meps25-v1 model uses it: race/ethnicity's
# influence belongs in aggregate fairness reporting, not in one patient's explanation (O50, O57).
NEVER_REASONS = {"racethx"}
MIN_EFFECT = 0.005           # an input must move the estimate by at least half a percentage point

# Plain-language names for reasons (rationale text and the agent's narration).
FEATURE_NAMES = {
    "sex": "sex", "racethx": "race and ethnicity", "regiony1": "region", "agey1x": "age",
    "inscovy1": "insurance", "povcaty1": "household income", "ipdisy1": "hospital stays in the past year",
    "ipngtdy1": "nights in hospital in the past year", "ertoty1": "emergency-room visits in the past year",
    "obtotvy1": "office visits in the past year", "optotvy1": "hospital outpatient visits in the past year",
    "hhtotdy1": "home-health days in the past year", "rxtoty1": "prescription fills in the past year",
    "totexpy1": "health care spending in the past year", "hibpdx": "high blood pressure",
    "chddx": "coronary heart disease", "angidx": "angina", "midx": "a past heart attack",
    "ohrtdx": "other heart disease", "strkdx": "a past stroke", "emphdx": "emphysema or COPD",
    "diabdx": "diabetes", "arthdx": "arthritis", "asthdx": "asthma", "choldx": "high cholesterol",
    # meps-portable-v2 (M12)
    "mcrevy1": "Medicare cover", "mcdevy1": "Medicaid cover", "n_icd": "the number of different diagnoses",
    "n_icd_chapters": "diagnoses across several body systems", "n_distinct_drugs": "the number of different medicines",
    "hfrs": "frailty indicated by the diagnoses", "charlson_approx": "comorbidity (Charlson score)",
    "elixhauser_vw_approx": "comorbidity (Elixhauser score)", "elixhauser_count_approx": "the number of comorbidities",
    "tokens_icd": "the particular diagnoses recorded",
}


class ArtifactNotFound(RuntimeError):
    """No artifact to serve."""


@dataclass
class Score:
    patient_ref: str
    probability: float
    comparison: float
    percentile: int
    reasons: list[str] = field(default_factory=list)         # feature names, most influential first


def find_artifact(contract: str = CONTRACT_VERSION) -> Path:
    """The artifact named by OUTCOME_PREDICTION_ARTIFACT (meps25-v1 only), else the newest for
    `contract` under the models directory."""
    import os
    if contract == CONTRACT_VERSION and (named := os.environ.get("OUTCOME_PREDICTION_ARTIFACT")):
        return Path(named)
    found = sorted(models_dir().glob(f"gbm-{contract}-*"))
    if not found:
        raise ArtifactNotFound(f"no gbm-{contract}-* artifact under {models_dir()} — train one "
                               "(meps25-v1: python -m outcome_prediction.model.train; meps-portable-v2: "
                               "outcome-prediction-lab promote) or set OUTCOME_PREDICTION_ARTIFACT")
    return found[-1]


class Scorer:
    """One promoted artifact, loaded once: its manifest verified before any deserialisation (O17),
    its promotion record verified before it is served (O33)."""

    def __init__(self, artifact_dir: Path | None = None):
        directory = Path(artifact_dir) if artifact_dir else find_artifact()
        self.promotion = verify_promotion(directory)             # refused -> the service does not start
        self.artifact: Artifact = load_artifact(directory)
        meta = self.artifact.metadata
        self.contract = meta.get("contract_version")
        if self.contract == CONTRACT_VERSION:
            self.inputs = list(FEATURES)
            self.typical = json.loads(REFERENCE.read_text())["typical"]
            self.blank = []
        elif self.contract == portable.CONTRACT_VERSION:
            self.inputs = list(meta["features"])
            self.typical = meta["typical"]
            self.blank = list(meta.get("blank_at_scoring") or [])
        else:
            raise ValueError(f"artifact contract {self.contract!r} is not served")
        self.label = meta.get("label")
        self.quantiles = meta["training_score_quantiles"]

    @property
    def model_id(self) -> str:
        return self.artifact.metadata["model_id"]

    def _X(self, rows: pd.DataFrame) -> pd.DataFrame:
        if self.contract == CONTRACT_VERSION:
            return feature_matrix(rows[FEATURES])
        X = rows[self.inputs].copy()
        X[self.blank] = np.nan          # scored as it was confirmed: these inputs blanked (O53)
        return X

    def _comparison_X(self, rows: pd.DataFrame):
        return comparison_matrix(rows) if self.contract == CONTRACT_VERSION else rows[self.inputs]

    def score(self, rows: pd.DataFrame, defaulted: dict[str, set[str]] | None = None) -> list[Score]:
        """Score contract rows (`patient_ref` + the contract's inputs). `defaulted` maps a
        patient_ref to the inputs filled by a default — those are never given as reasons."""
        defaulted = defaulted or {}
        rows = rows.reset_index(drop=True)
        p = self.artifact.model.predict_proba(self._X(rows))[:, 1]
        comp = self.artifact.comparison.predict_proba(self._comparison_X(rows))[:, 1]
        reasons = self._reasons(rows, p, defaulted)
        return [Score(patient_ref=str(ref), probability=float(p[i]), comparison=float(comp[i]),
                      percentile=risk_percentile(float(p[i]), self.quantiles), reasons=reasons[i])
                for i, ref in enumerate(rows.patient_ref)]

    def _reasons(self, rows: pd.DataFrame, p: np.ndarray, defaulted: dict[str, set[str]]) -> list[list[str]]:
        """Every row's occlusion variants in ONE prediction call (a 1,000-row batch is one call)."""
        variants, owner, feature = [], [], []
        for i, row in rows.iterrows():
            skip = defaulted.get(str(row.patient_ref), set()) | NEVER_REASONS | set(self.blank)
            for f in self.inputs:
                value = row[f]
                missing = value is None or (isinstance(value, float) and np.isnan(value))
                if f not in skip and not missing and value != self.typical[f]:
                    variants.append({**{c: row[c] for c in self.inputs}, f: self.typical[f]})
                    owner.append(i)
                    feature.append(f)
        out: list[list[str]] = [[] for _ in range(len(rows))]
        if not variants:
            return out
        q = self.artifact.model.predict_proba(self._X(pd.DataFrame(variants, columns=self.inputs)))[:, 1]
        effect = pd.DataFrame({"row": owner, "feature": feature, "effect": p[owner] - q})
        effect = effect[effect.effect >= MIN_EFFECT].sort_values(["row", "effect"], ascending=[True, False], kind="stable")
        for i, group in effect.groupby("row"):
            out[i] = list(group.feature[:TOP_REASONS])
        return out
