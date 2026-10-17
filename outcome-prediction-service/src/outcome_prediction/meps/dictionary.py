"""FR-D3: dump every variable in a MEPS Stata file — label, storage type, value range,
negative (missing) codes, value labels, string lengths.

Named `dictionary`, not `inspect`, so running it as a script can't shadow the standard
library's `inspect` module.

Storage types are only exposed through pandas' private StataReader attributes `_varlist`,
`_typlist`, `_lbllist` (stable in pandas 2.x and 3.x — prototype-baseline.md §3.4). The
unit tests exercise them, so a pandas upgrade that removes them fails in CI, not silently.

Usage:
    python -m outcome_prediction.meps.dictionary 252 [--out h252_dictionary.csv]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from pandas.io.stata import StataReader

from outcome_prediction.meps.download import fetch
from outcome_prediction.settings import processed_dir

STORAGE = {"b": "int8", "h": "int16", "l": "int32", "f": "float32", "d": "float64"}


def _storage_name(code) -> str:
    # Numeric types are single-letter codes; an integer N means a fixed-width strN.
    return f"str{code}" if isinstance(code, int) else STORAGE.get(code, f"str{code}")


def variable_dictionary(dta: Path) -> pd.DataFrame:
    with StataReader(dta) as reader:
        df = reader.read(convert_categoricals=False)
        types = dict(zip(reader._varlist, reader._typlist))
        label_names = dict(zip(reader._varlist, reader._lbllist))
        value_labels = reader.value_labels()
        variable_labels = reader.variable_labels()

    rows = []
    for var in df.columns:
        storage = _storage_name(types[var])
        series = df[var]
        row = {"variable": var, "label": variable_labels.get(var, ""), "storage": storage}
        if storage.startswith("str"):
            text = series.dropna().astype(str)
            text = text[text.str.len() > 0]
            row.update(max_len=int(text.str.len().max()) if len(text) else 0,
                       n_unique=int(text.nunique()),
                       examples="; ".join(map(str, text.unique()[:5])))
        else:
            pos = series[series >= 0]
            neg = sorted(series[series < 0].unique().tolist())
            row.update(min=pos.min() if len(pos) else None,
                       max=pos.max() if len(pos) else None,
                       n_unique=int(pos.nunique()),
                       negative_codes=" ".join(map(str, neg[:8])))
            labels = value_labels.get(label_names.get(var, ""), {})
            row["value_labels"] = "; ".join(
                f"{k}={v}" for k, v in labels.items() if k >= 0)[:500]
        rows.append(row)
    return pd.DataFrame(rows)


def storage_counts(dictionary: pd.DataFrame) -> dict[str, int]:
    return {k: int(v) for k, v in dictionary.storage.value_counts().items()}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=int, help="MEPS file number, e.g. 252")
    parser.add_argument("--out", type=Path, default=None,
                        help="CSV path (default: <data>/processed/h{n}_dictionary.csv)")
    args = parser.parse_args(argv)

    dictionary = variable_dictionary(fetch(args.file))
    out = args.out or processed_dir() / f"h{args.file}_dictionary.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    dictionary.to_csv(out, index=False)
    print(f"{len(dictionary)} variables written to {out}")
    print(storage_counts(dictionary))


if __name__ == "__main__":
    main()
