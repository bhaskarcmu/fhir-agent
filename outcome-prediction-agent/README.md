# outcome-prediction-agent

Ask for a patient's 12-month hospitalization risk in plain language (Phase 8 M8). Built on
`agent-platform` (Phase 6); self-hosted Llama by default, so no patient data leaves the host
(decisions O15, O16). Planning and decisions: [`docs/phase8/`](../docs/phase8/README.md).

```bash
pip install -e agent-platform -e outcome-prediction-agent
OUTCOME_PREDICTION_URL=http://localhost:8005 \
  outcome-prediction-agent --query "What is the hospitalization risk for Jane Doe?"
```

Needs the scoring service (`outcome-prediction-service`, port 8005) and, by default, Ollama with
`llama3.2:1b`. `LLM_PROVIDER` selects another model (see `agent_platform.providers`).

## How it stays grounded (O69)

The language model **orchestrates**; code decides what the clinician sees.

| Rule | Where |
|---|---|
| Only the service's published tools are offered (`find_patient`, `get_hospitalization_risk`, `get_model_card`); the service validates every call | `service.py`, the service's `tools.py` |
| Questions about more than one patient ("rank everyone over 20%") are refused before any tool is called | `agent.py` |
| A risk call is accepted only for a patient id that `find_patient` returned or the clinician typed — a made-up id is refused | `agent.py` |
| One match is scored by code; several go back to the clinician | `agent.py` |
| The model card answers only questions about the model | `agent.py` |
| Every reply is built from the service's output — probability, comparison, percentile, reasons, warnings, model version, the planning-aid note — plus fixed notices with no numbers | `explain.py` |
| Every reply is checked: a number the service didn't return means the reply is withheld | `explain.grounded` |
| The model's own text is never shown | `agent.py` |

"Adjust for her new diagnosis" and "what if she were 40" get the service's unchanged estimate plus
a notice that it can't be adjusted; "is that high risk?" gets the estimate plus a notice that no
bands have been clinically agreed (O24).

## Files

| File | Does |
|---|---|
| `agent.py` | The tool-use loop and its guards; CLI |
| `explain.py` | Replies, notices, the outcome enum, the grounding check |
| `service.py` | HTTP client for the service's tools — no model code, no FHIR client |
| `policy.md` | Scope and rules, loaded into the system prompt |
| `testing.py` | A scripted model and a replay of the service's recorded outputs |

## Tests

```bash
pytest outcome-prediction-agent/tests -q       # needs Ollama + llama3.2:1b for test_live_model.py
```

`test_risk_agent.py` and `test_risk_explain.py` are deterministic (scripted model). `test_live_model.py`
runs the grounding and adversarial scenarios against the real self-hosted model and — like
`mcp-agent`'s live tests (Phase 6 H50) — fails rather than skips without Ollama. CI runs them in
the `phase8 agent` job. The service's outputs are recorded from the real service
(`tests/record_service_outputs.py`); its tool definitions are checked against the service by the
service's own tests.
