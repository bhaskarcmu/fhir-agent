"""Character n-grams vs words for messy drug names (round 002, concept: TF-IDF on text).

The task a FHIR integration actually faces: a medication arrives as free text — here MEPS's
pharmacy-recorded RXNAME, often abbreviated ("METOPROL TAR", "HYDROCODON/APAP") — and must be
mapped to a therapeutic class. Train on names seen in 2016–2020; test on names that FIRST appear in
2021–2022, so an exact-lookup table cannot know them and only text similarity can help.

Compared: exact lookup (by construction knows none of the unseen names), word TF-IDF + 1-nearest
neighbour, character n-gram TF-IDF + 1-nearest neighbour. Accuracy against the Multum class AHRQ
attached to the same fill (most specific level), and against the top-level class.
"""
from __future__ import annotations

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

from outcome_prediction_lab.data import PRESCRIBED, _rx_class, read_meps

SUPPRESSED = {"-15", "-9", "-8", "-7", "-1", "", "nan"}


def name_class_pairs() -> pd.DataFrame:
    """Distinct (year, pharmacy name) with the majority class at the most specific level and at
    the top level (TC1)."""
    rows = []
    for year, fid in PRESCRIBED.items():
        d = read_meps(fid)
        d = d.assign(name=d.RXNAME.astype(str).str.strip().str.upper(), cls=_rx_class(d, "most_specific"),
                     top=pd.to_numeric(d.TC1, errors="coerce"))
        d = d[~d.name.isin(SUPPRESSED) & d.cls.notna() & (d.top > 0)]
        g = d.groupby("name").agg(cls=("cls", lambda s: s.mode().iloc[0]), top=("top", lambda s: s.mode().iloc[0]))
        rows.append(g.reset_index().assign(year=year))
    return pd.concat(rows, ignore_index=True)


def _nn_accuracy(vectorizer, train: pd.DataFrame, test: pd.DataFrame) -> dict:
    Xtr = vectorizer.fit_transform(train.name)
    Xte = vectorizer.transform(test.name)
    nn = NearestNeighbors(n_neighbors=1, metric="cosine").fit(Xtr)
    dist, idx = nn.kneighbors(Xte)
    matched = train.iloc[idx[:, 0]].reset_index(drop=True)
    no_signal = (Xte.getnnz(axis=1) == 0)                   # nothing in common with any training name
    return {"class_accuracy": float((matched.cls.to_numpy() == test.cls.to_numpy()).mean()),
            "top_class_accuracy": float((matched.top.to_numpy() == test.top.to_numpy()).mean()),
            "share_with_no_overlap": float(no_signal.mean()),
            "examples": [{"name": n, "matched": m, "correct_class": bool(a == b)}
                         for n, m, a, b in list(zip(test.name, matched.name, matched.cls, test.cls))[:12]]}


def run() -> dict:
    pairs = name_class_pairs()
    train_names = pairs[pairs.year <= 2020].drop_duplicates("name", keep="last")
    later = pairs[pairs.year >= 2021].drop_duplicates("name", keep="last")
    unseen = later[~later.name.isin(set(train_names.name))].reset_index(drop=True)
    seen = later[later.name.isin(set(train_names.name))]
    exact_on_seen = float((seen.merge(train_names, on="name", suffixes=("", "_tr"))
                           .pipe(lambda m: (m.cls == m.cls_tr).mean())))
    return {
        "n_training_names": int(len(train_names)), "n_test_names_unseen": int(len(unseen)),
        "n_test_names_seen_before": int(len(seen)),
        "exact_lookup": {"class_accuracy_on_unseen": 0.0, "class_accuracy_on_seen": exact_on_seen},
        "word_tfidf_1nn": _nn_accuracy(TfidfVectorizer(analyzer="word", token_pattern=r"[A-Z0-9]+",
                                                       lowercase=False), train_names, unseen),
        "char_ngram_tfidf_1nn": _nn_accuracy(TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                                             lowercase=False), train_names, unseen),
    }
