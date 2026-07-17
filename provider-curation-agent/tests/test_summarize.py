from provider_curation_agent.summarize import render_summary


def _run(**overrides):
    run = {
        "run_id": "RUN-1", "states_pulled": ["NC"], "states_freshly_fetched": [],
        "records_added": 10, "records_updated": 0, "records_flagged": 0,
        "anomaly_breakdown": {}, "sample_anomalies": [],
    }
    run.update(overrides)
    return run


def test_basic_counts_present():
    text = render_summary(_run())
    assert "RUN-1" in text
    assert "10 record(s) added" in text
    assert "0 updated, 0 anomalies flagged" in text


def test_no_anomalies_says_so():
    text = render_summary(_run())
    assert "No anomalies flagged." in text


def test_anomaly_breakdown_rendered():
    text = render_summary(_run(
        records_flagged=3,
        anomaly_breakdown={"missing_coordinate": 2, "missing_taxonomy": 1},
    ))
    assert "2 missing_coordinate" in text
    assert "1 missing_taxonomy" in text


def test_freshly_fetched_states_mentioned():
    text = render_summary(_run(states_freshly_fetched=["CA", "MT"]))
    assert "Freshly fetched from NPPES this run: CA, MT." in text


def test_sample_anomalies_included_but_capped_at_three():
    samples = [{"npi": str(i) * 10, "flag_type": "missing_taxonomy", "detail": f"d{i}"} for i in range(5)]
    text = render_summary(_run(records_flagged=5, sample_anomalies=samples))
    assert text.count("missing_taxonomy:") == 3


def test_never_fabricates_counts_not_in_input():
    # The renderer must only reflect what's in the dict -- no derived/invented numbers.
    run = _run(records_added=7, records_updated=2, records_flagged=1,
               anomaly_breakdown={"missing_taxonomy": 1})
    text = render_summary(run)
    assert "7 record(s) added, 2 updated, 1 anomalies flagged" in text
