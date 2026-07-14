from claims_agent.explain import render_explanation


def _decision(outcome, reasons=None, all_findings=None, pricing=None):
    reasons = reasons or []
    return {
        "decisionId": "DEC-C1",
        "outcome": outcome,
        "reasons": reasons,
        "allFindings": all_findings if all_findings is not None else reasons,
        "pricing": pricing,
    }


def test_approved_with_pricing():
    d = _decision("APPROVED", pricing={
        "paid": True, "totalAmount": 241.50, "patientPay": 48.30,
        "planPay": 193.20, "authNumber": "RX1"})
    text = render_explanation(d)
    assert "approved" in text.lower()
    assert "241.50" in text and "48.30" in text
    assert "DEC-C1" in text


def test_denied_multi_reason_aggregates_and_notes_secondary():
    d = _decision(
        "DENIED",
        reasons=[{"code": "non-formulary", "message": "Drug is not on the plan formulary."}],
        all_findings=[
            {"code": "non-formulary", "message": "Drug is not on the plan formulary."},
            {"code": "quantity-limit-exceeded", "message": "Requested quantity exceeds the limit."},
        ],
    )
    text = render_explanation(d)
    assert "denied" in text.lower()
    assert "not on the plan formulary" in text
    assert "Also noted" in text and "quantity" in text.lower()


def test_pended_mentions_prior_auth():
    d = _decision("PENDED", reasons=[
        {"code": "prior-auth-required", "message": "Prior authorization is required."}])
    text = render_explanation(d)
    assert "pended" in text.lower()
    assert "prior authorization" in text.lower()


def test_routed_mentions_review_task():
    d = _decision("ROUTED_FOR_REVIEW", reasons=[
        {"code": "step-therapy-required", "message": "Step therapy required."}])
    text = render_explanation(d)
    assert "manual review task" in text.lower()
