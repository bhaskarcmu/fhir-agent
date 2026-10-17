"""Shared fixtures.

Unit tests use tiny synthetic Stata files shaped like MEPS. Tests that need real data or the
GCS emulator ask for a session fixture below, which **populates whatever is missing** —
decisions.md O44 — so a single test, a file, or the whole suite behaves the same, locally or
in CI:

  meps_cache          all seven panels in the MEPS cache, fetched from the local archive, AHRQ,
                      or configured mirrors and verified against meps-manifest.json
  gcs_emulator        a reachable GCS emulator: STORAGE_EMULATOR_HOST if it answers, otherwise
                      a fake-gcs-server container started for the session and removed after
  meps_emulator_bucket  the emulator bucket `phase8-reference-data`, created if absent and
                      topped up with every manifest data zip it lacks

If data can't be obtained the test FAILS, loudly — a silent skip would let CI pass without
having exercised it. To work offline, set OUTCOME_PREDICTION_TESTS_OFFLINE=1: then these
fixtures skip instead of fetching or starting anything.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
import warnings
from pathlib import Path

import pandas as pd
import pytest

from outcome_prediction.meps import LONGITUDINAL_PANELS
from outcome_prediction.settings import meps_cache_dir

DX_Y1 = ["HIBPDXY1", "CHDDXY1", "ANGIDXY1", "MIDXY1", "OHRTDXY1", "STRKDXY1",
         "EMPHDXY1", "DIABDXY1", "ARTHDXY1", "ASTHDXY1", "CHOLDXY1"]


def person(dupersid: str, panel: int, *, age=50, ipdis1=0, ipdis2=0, dx=None) -> dict:
    """One synthetic MEPS person. `dx` maps a DX_Y1 column to its raw MEPS code
    (1 yes, 2 no, negative = missing); unlisted flags default to 2 (no)."""
    row = {
        "DUPERSID": dupersid, "PANEL": panel, "SEX": 1, "RACETHX": 2, "REGIONY1": 3,
        "AGEY1X": age, "INSCOVY1": 1, "POVCATY1": 4, "IPDISY1": ipdis1, "IPNGTDY1": 0,
        "ERTOTY1": 0, "OBTOTVY1": 3, "OPTOTVY1": 0, "HHTOTDY1": 0, "RXTOTY1": 5,
        "TOTEXPY1": 1200, "IPDISY2": ipdis2, "LONGWT": 1000.5, "VARSTR": 1, "VARPSU": 1,
    }
    row.update({col: 2 for col in DX_Y1})
    row.update(dx or {})
    return row


@pytest.fixture
def write_panel(tmp_path):
    """Write synthetic people to a .dta file; optionally rename columns to mimic
    year-to-year drift (e.g. DIABDXY1 -> DIABDXY1_M18)."""
    def _write(name: str, people: list[dict], rename: dict | None = None) -> Path:
        df = pd.DataFrame(people)
        int_cols = [c for c in df.columns if c not in ("DUPERSID", "LONGWT")]
        df[int_cols] = df[int_cols].astype("int32")
        if rename:
            df = df.rename(columns=rename)
        path = tmp_path / name
        df.to_stata(path, write_index=False)
        return path
    return _write


def synthetic_table(per_panel: int = 300, seed: int = 0) -> pd.DataFrame:
    """A modelling table shaped exactly like meps.build's output (same columns, same order),
    with a real age / prior-stay signal so models have something to learn. Panels 21–27."""
    import numpy as np

    from outcome_prediction.model import FEATURES, LABEL

    rng = np.random.default_rng(seed)
    n = per_panel * 7
    t = pd.DataFrame({"dupersid": np.arange(n), "panel": np.repeat(np.arange(21, 28), per_panel)})
    t["sex"] = rng.integers(1, 3, n)
    t["racethx"] = rng.integers(1, 6, n)
    t["regiony1"] = rng.choice([-1, 1, 2, 3, 4], n)          # -1: a MEPS missing code
    t["agey1x"] = rng.integers(18, 86, n)
    t["inscovy1"] = rng.integers(1, 4, n)
    t["povcaty1"] = rng.integers(1, 6, n)
    t["ipdisy1"] = rng.binomial(1, 0.12, n) * rng.integers(1, 3, n)
    t["ipngtdy1"] = t["ipdisy1"] * rng.integers(1, 6, n)
    for col, lam in (("ertoty1", 0.4), ("obtotvy1", 4), ("optotvy1", 0.5),
                     ("hhtotdy1", 0.1), ("rxtoty1", 12)):
        t[col] = rng.poisson(lam, n)
    t["totexpy1"] = rng.integers(0, 20000, n)
    for col in FEATURES[14:]:
        t[col] = rng.binomial(1, 0.15, n)
    t["longwt"] = rng.uniform(500, 5000, n)
    t["varstr"] = rng.integers(1, 100, n)
    t["varpsu"] = rng.integers(1, 3, n)
    logit = -4.0 + 0.035 * t["agey1x"] + 1.4 * (t["ipdisy1"] > 0)
    t[LABEL] = rng.binomial(1, 1 / (1 + np.exp(-logit)))
    order = ["dupersid", "panel", *FEATURES[:14], "longwt", "varstr", "varpsu", *FEATURES[14:], LABEL]
    return t[order]


OFFLINE_ENV = "OUTCOME_PREDICTION_TESTS_OFFLINE"
# Must match the gcs-emulator image in docker-compose.yml (checked by test_meps_mirror_emulator).
GCS_EMULATOR_IMAGE = "fsouza/fake-gcs-server:1.56.1"
EMULATOR_BUCKET = "phase8-reference-data"


def _offline() -> bool:
    return os.environ.get(OFFLINE_ENV, "").strip().lower() in ("1", "true", "yes")


@pytest.fixture(scope="session")
def meps_cache() -> Path:
    """The real MEPS cache with all seven panels, populated on demand (O44)."""
    from outcome_prediction.meps.download import ChecksumMismatch, SourceUnavailable, fetch

    cache = meps_cache_dir()
    missing = [n for n in LONGITUDINAL_PANELS.values() if not (cache / f"h{n}.dta").exists()]
    if missing and _offline():
        pytest.skip(f"{OFFLINE_ENV} is set and the MEPS cache at {cache} lacks "
                    f"{', '.join(f'h{n}.dta' for n in missing)}")
    try:
        for n in LONGITUDINAL_PANELS.values():   # verifies present files, fetches missing ones
            try:
                fetch(n, cache)
            except ChecksumMismatch:
                # A cached file that doesn't match the manifest is wrong data: set it aside
                # (kept, for investigation) and fetch a verified original. The pipeline CLIs
                # still refuse in this situation — there, a human should look first.
                bad = cache / f"h{n}.dta"
                kept = bad.with_name(f"{bad.name}.mismatch-{int(time.time())}")
                bad.rename(kept)
                warnings.warn(f"{bad.name} did not match meps-manifest.json; moved to {kept.name} "
                              f"and re-fetched a verified original", stacklevel=1)
                fetch(n, cache)
    except SourceUnavailable as exc:
        pytest.fail(f"could not populate the MEPS cache at {cache}:\n{exc}", pytrace=False)
    return cache


def _reachable(host: str) -> bool:
    try:
        urllib.request.urlopen(f"{host}/storage/v1/b", timeout=3)
        return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def gcs_emulator():
    """Base URL of a reachable GCS emulator, exported as STORAGE_EMULATOR_HOST for the session.
    Reuses a running one (docker compose, CI); otherwise starts a throwaway container."""
    host = os.environ.get("STORAGE_EMULATOR_HOST")
    if host and _reachable(host):
        yield host
        return
    if _offline():
        pytest.skip(f"{OFFLINE_ENV} is set and no GCS emulator is reachable")
    if shutil.which("docker") is None:
        pytest.fail("no GCS emulator is reachable and Docker isn't available to start one; "
                    f"start one (docker compose --profile phase8 up -d gcs-emulator) or set {OFFLINE_ENV}=1",
                    pytrace=False)

    name = f"phase8-test-gcs-{os.getpid()}"
    started = subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::4443", GCS_EMULATOR_IMAGE,
         "-scheme", "http", "-port", "4443", "-backend", "memory"],
        capture_output=True, text=True)
    if started.returncode != 0:
        pytest.fail(f"could not start the GCS emulator container: {started.stderr.strip()}", pytrace=False)
    try:
        port = subprocess.run(["docker", "port", name, "4443/tcp"], capture_output=True,
                              text=True, check=True).stdout.split(":")[-1].strip()
        host = f"http://127.0.0.1:{port}"
        for _ in range(60):
            if _reachable(host):
                break
            time.sleep(0.5)
        else:
            pytest.fail(f"GCS emulator container {name} never became reachable at {host}", pytrace=False)
        previous = os.environ.get("STORAGE_EMULATOR_HOST")
        os.environ["STORAGE_EMULATOR_HOST"] = host
        yield host
        if previous is None:
            os.environ.pop("STORAGE_EMULATOR_HOST", None)
        else:
            os.environ["STORAGE_EMULATOR_HOST"] = previous
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True)


@pytest.fixture(scope="session")
def meps_emulator_bucket(gcs_emulator, meps_cache):
    """`gs://phase8-reference-data` on the emulator, holding every manifest data zip — created
    if absent, topped up if incomplete, then verified (O44). Documentation is left out: AHRQ
    may edit its HTML pages, and a cosmetic edit shouldn't fail a data test."""
    from google.api_core.exceptions import Conflict
    from google.cloud import storage

    from outcome_prediction.meps.download import ensure_archive
    from outcome_prediction.meps.manifest import load_manifest
    from outcome_prediction.meps.mirror import from_uri, push, verify

    try:
        storage.Client(project="local").create_bucket(EMULATOR_BUCKET)
    except Conflict:
        pass                                            # already exists: top it up below
    manifest = load_manifest()
    archive = meps_cache / "archive"
    ensure_archive(manifest, archive, include_docs=False)
    mirror = from_uri(f"gs://{EMULATOR_BUCKET}")
    push(manifest, archive, [mirror], include_docs=False)
    problems = verify(manifest, [mirror], include_docs=False)
    if problems:
        pytest.fail("emulator bucket failed verification:\n" + "\n".join(problems), pytrace=False)
    return mirror
