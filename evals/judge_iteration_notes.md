# Course lesson: fixing judge tests

Implemented in `models.py`, `doc_agent.py`, `tests/judge.py`, the cost-test infrastructure, and Section 25 of `notebooks/02-rag-chemical-triage.ipynb`.

- Typed rule/passed/explanation checks, with defaults for reading earlier saved responses. New explicit checklists are validated; self-reported success is not proof.
- Plain-text response rendering preserves literal code instead of JSON escaping. The judge evaluates the answer independently of claimed self-check success.
- Instructions adapt to supplied variables/columns, label proposed analyst code, distinguish uv add from uv sync, and retain exact quoted threat evidence.
- Research budgets reserve room for final output. Invalid references trigger bounded corrections. Interrupted runs preserve known provider usage where available.
- Four-worker tests write isolated JSONL journals and merge by unique record/run IDs. Prior runs remain in the ledger; current totals are isolated without deleting history.
- Agent/judge models are independently configurable; no stronger-model comparison was performed in the latest pass.

## Measured live run, 2026-11-12

`python -m pytest tests/test_user_scenarios.py -m live --run-live -n 4 --tb=short -q`

Result: **2 passed, 3 failed** in 44.25 seconds; 177,731 input tokens, 4,978 output tokens, including 8,704 cached input tokens. Recorded token estimate: **$0.028994**. This is not an invoice or the total cost of all development runs.

| Scenario | Result | Observation |
|---|---|---|
| ambiguous-persistence | Passed | Passed the configured contract and judge criteria for this run |
| uv-package-management | Passed | Passed the configured contract and judge criteria for this run |
| off-topic-chess | Failed | Correct scoped refusal, but no search and an empty checklist; current runtime enforcement did not prevent this live outcome |
| python-formatting | Failed | Multi-keyword call remained on one line; judge also confused some definition/call spacing. Inspect the literal code before accepting every judge rationale |
| existing-indicator-dataframe | Failed | Provenance/context verdict failed; response also introduced fabricated example indicators and unsupported maliciousness framing |

Repeated live attempts showed variation and occasional request-limit failures. The present changes implement the lesson, but do not make all quality scenarios pass. Do not weaken requirements or treat a positive checklist as a substitute for evidence. Investigate streaming/final-output policy enforcement next, then correct contextual output and compare judge verdicts with human labels.

## Run locally

```bash
uv run pytest -m 'not live' -q
make tests-judge
# Paid calls:
uv run pytest tests/test_user_scenarios.py -m live --run-live -n 4 -q
# Optional paid model comparison (not executed in the latest run):
uv run pytest tests/test_user_scenarios.py -m live --run-live --agent-model openai:gpt-4o --judge-model openai:gpt-4o -q
```

Scenario answers/failures are in `outputs/scenario_runs/`; judge feedback is in `outputs/judge_feedback/`; recorded usage is in `outputs/test_usage.jsonl`. These generated artifacts are local and ignored by Git. Existing triage weights, PIR definitions, analyst decisions and approval gates are preserved.
