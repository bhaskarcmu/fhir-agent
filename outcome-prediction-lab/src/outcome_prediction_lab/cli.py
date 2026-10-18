"""`outcome-prediction-lab` — the lab's command line (docs/phase8/experimentation-protocol.md).

    outcome-prediction-lab run        <round> <config-name> [<config-name> ...]   CV on training panels
    outcome-prediction-lab compare    <round> [--metric auroc]                    table of a round's runs
    outcome-prediction-lab confirm    <round> <config-name> [--record "why"]      ONE logged test look
    outcome-prediction-lab card       <round> <config-name>                       model card
    outcome-prediction-lab scorecard  <round> <config-name> [--criteria f.json]   target scorecard
    outcome-prediction-lab promote    <round> <config-name> --decision O<n>       promotion record
    outcome-prediction-lab explain    <round> <config-name> (--patient ID | --sample N)
    outcome-prediction-lab drug-names <round>                                     drug-name text experiment
    outcome-prediction-lab notebooks-check | notebooks-strip <file.ipynb>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def _cmd_run(a):
    from outcome_prediction_lab import runs
    for name in a.names:
        r = runs.run(a.round, name)
        cv = r["cv"]
        key = "auroc" if "auroc" in cv else "spearman"
        base = r.get("cv_baseline", {}).get(key)
        print(f"{name:<40} CV {key} {cv[key]:.4f}" + (f"   baseline {base:.4f}" if base is not None else ""))


def _cmd_compare(a):
    from outcome_prediction_lab import runs
    print(runs.compare(a.round, a.metric))


def _cmd_confirm(a):
    from outcome_prediction_lab import holdout, runs
    if a.record:
        holdout.record(a.round, a.name, a.record)
    r = runs.confirm(a.round, a.name)
    print(json.dumps({"test": r["test"], "test_baseline": r.get("test_baseline")}, indent=2))


def _cmd_card(a):
    from outcome_prediction_lab import runs
    print(runs.card(a.round, a.name))


def _cmd_scorecard(a):
    from outcome_prediction_lab import runs
    print(runs.scorecard(a.round, a.name, a.criteria))


def _cmd_promote(a):
    from outcome_prediction_lab import runs
    print(runs.promote(a.round, a.name, a.decision))


def _cmd_explain(a):
    from outcome_prediction_lab import narrate, runs
    from outcome_prediction_lab.evaluate import TEST_PANELS
    from outcome_prediction_lab.vocabulary import build_vocabulary
    frame = runs.lab_frame()
    path = runs.fitted_path(a.round, a.name)
    if path.exists():
        import joblib
        cfg, pipe = runs.load_config(runs.config_path(a.round, a.name)), joblib.load(path)
    else:                              # fit on training panels only — no metrics, no test look
        cfg, pipe = runs.fit_on_training_panels(a.round, a.name, frame)
    narrator = narrate.Narrator(pipe, cfg, frame, build_vocabulary())
    test = frame[frame.panel.isin(TEST_PANELS)].reset_index(drop=True)
    if a.all:                          # every test-panel patient -> gitignored CSV (derived output)
        from outcome_prediction.settings import reports_dir
        rows = []
        for i in range(len(test)):
            e = narrator.explain(test.iloc[[i]])
            rows.append({"panel": int(test.panel.iloc[i]), "dupersid": test.dupersid.iloc[i],
                         "predicted": round(e["predicted"], 4), "narrative": e["narrative"]})
        dest = reports_dir() / f"narratives-{a.round}-{a.name}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        import pandas as pd
        pd.DataFrame(rows).to_csv(dest, index=False)
        print(f"{len(rows):,} narratives -> {dest}")
        return
    if a.patient:
        rows = test[test.dupersid == a.patient]
        if rows.empty:
            sys.exit(f"no test-panel patient {a.patient}")
        picks = [rows.index[0]]
    else:
        scored = test.copy()
        scored[cfg.get("simulate_missing_at_scoring") or []] = np.nan     # rank as production would
        risk = pipe.predict_proba(scored)[:, 1]
        order = risk.argsort()
        qs = [0.05, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 0.999][: a.sample]
        picks = [int(order[int(q * (len(order) - 1))]) for q in qs]
    out = []
    for i in picks:
        e = narrator.explain(test.iloc[[i]])
        out.append(e["narrative"])
        print(e["narrative"], "\n")
    if a.write:
        dest = runs.round_dir(a.round) / "explanations" / f"{a.name}-examples.md"
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(f"# Example patient explanations — `{a.name}`\n\nTest-panel patients across the risk "
                        "range (5th to 99.9th percentile of predicted risk). Outcomes are deliberately "
                        "not shown.\n\n" + "\n\n".join(f"{n}. {t}" for n, t in enumerate(out, 1)) + "\n")
        print(dest)


def _cmd_drug_names(a):
    from outcome_prediction_lab import drugnames, runs
    r = drugnames.run()
    dest = runs.round_dir(a.round) / "drug_names.json"
    dest.write_text(json.dumps(r, indent=2) + "\n")
    for k in ("word_tfidf_1nn", "char_ngram_tfidf_1nn"):
        print(k, {x: round(r[k][x], 3) for x in ("class_accuracy", "top_class_accuracy", "share_with_no_overlap")})
    print(dest)


def _cmd_nb_check(a):
    from outcome_prediction_lab import notebooks
    problems = notebooks.check()
    print("\n".join(problems) if problems else "notebooks clean: no outputs, no execution counts")
    if problems:
        sys.exit(1)


def _cmd_nb_strip(a):
    from outcome_prediction_lab import notebooks
    for f in a.files:
        notebooks.strip(Path(f))
        print(f"stripped {f}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="outcome-prediction-lab", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("run"); s.add_argument("round"); s.add_argument("names", nargs="+"); s.set_defaults(fn=_cmd_run)
    s = sub.add_parser("compare"); s.add_argument("round"); s.add_argument("--metric"); s.set_defaults(fn=_cmd_compare)
    s = sub.add_parser("confirm"); s.add_argument("round"); s.add_argument("name")
    s.add_argument("--record", metavar="WHY", help="append the ledger entry first (the look is then logged)")
    s.set_defaults(fn=_cmd_confirm)
    s = sub.add_parser("card"); s.add_argument("round"); s.add_argument("name"); s.set_defaults(fn=_cmd_card)
    s = sub.add_parser("scorecard"); s.add_argument("round"); s.add_argument("name")
    s.add_argument("--criteria", type=Path, help="JSON of person-scored criteria"); s.set_defaults(fn=_cmd_scorecard)
    s = sub.add_parser("promote"); s.add_argument("round"); s.add_argument("name")
    s.add_argument("--decision", required=True); s.set_defaults(fn=_cmd_promote)
    s = sub.add_parser("explain"); s.add_argument("round"); s.add_argument("name")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--patient"); g.add_argument("--sample", type=int)
    g.add_argument("--all", action="store_true", help="every test-panel patient, to a gitignored CSV")
    s.add_argument("--write", action="store_true", help="also write rounds/<round>/explanations/<name>-examples.md")
    s.set_defaults(fn=_cmd_explain)
    s = sub.add_parser("drug-names"); s.add_argument("round"); s.set_defaults(fn=_cmd_drug_names)
    s = sub.add_parser("notebooks-check"); s.set_defaults(fn=_cmd_nb_check)
    s = sub.add_parser("notebooks-strip"); s.add_argument("files", nargs="+"); s.set_defaults(fn=_cmd_nb_strip)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
