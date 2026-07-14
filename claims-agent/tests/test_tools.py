import json

import httpx

from claims_agent.tools import ClaimsClient, execute_tool

DECISION = {"decisionId": "DEC-C1", "outcome": "APPROVED", "reasons": [],
            "allFindings": [], "pricing": None}


def _client(handler) -> ClaimsClient:
    return ClaimsClient(base_url="http://claims.test",
                        client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_adjudicate_posts_to_claims_service_and_returns_decision():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=DECISION)

    client = _client(handler)
    out = client.adjudicate({"claimId": "C1", "rxcui": "29046"})

    assert out == DECISION
    assert seen["url"].endswith("/claims/adjudicate")
    assert seen["body"]["claimId"] == "C1"


def test_execute_tool_returns_decision_json():
    client = _client(lambda req: httpx.Response(200, json=DECISION))
    result = execute_tool("adjudicate_claim", {"claim": {"claimId": "C1"}}, client)
    assert json.loads(result)["outcome"] == "APPROVED"


def test_execute_tool_unknown_tool_is_error():
    client = _client(lambda req: httpx.Response(200, json=DECISION))
    assert "error" in json.loads(execute_tool("nope", {}, client))


def test_execute_tool_handles_service_failure_gracefully():
    client = _client(lambda req: httpx.Response(503, text="down"))
    result = json.loads(execute_tool("adjudicate_claim", {"claim": {}}, client))
    assert "error" in result  # never raises into the agent loop
