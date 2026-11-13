# Turn a user session into test cases

Use the existing CTI chat app, write or dictate what you asked, what you expected and what actually happened. Add the scenario to `evals/data/user_session_cases.json`; parameterized pytest tests load it without copying another test function. Do not store API keys or unnecessary private data in notes.

The five cases were adapted from the course. The latest measured four-worker live run on 2026-11-12 passed two and failed three; results vary across runs:

| Case | What to watch | Live observation |
|---|---|---|
| ambiguous-persistence | Cyber persistence interpretation; CTI follow-ups | Passed latest live run |
| python-formatting | Proposed Python formatting, separate from quoted attack commands | Failed: multi-keyword call formatting; inspect judge verdict against literal code |
| off-topic-chess | Scoped refusal, low report-support confidence, no irrelevant references, CTI follow-ups | Failed: scoped refusal omitted required search |
| existing-indicator-dataframe | Actually uses existing indicators_df columns instead of starting over | Failed: provenance/context criterion; response also proposed fabricated example indicators |
| uv-package-management | Proposed dependency instructions use uv; no unnecessary installation | Passed latest live run |

For each manual session record the exact query, observed answer/tool activity, expected behavior, why it matters, and report/context available to the agent. AI assistance can turn those notes into a case matching the existing JSON schema. Review generated criteria before running them; ambiguous or contradictory requirements make poor tests.

Formatting rules apply to proposed Python analysis code. They must not alter attacker commands quoted as evidence. The current agent is report-grounded, so a request for generated Python may reveal a scope/capability gap. Preserve that failure and decide the desired product behavior before changing instructions. Do not treat every refusal as a bug or rewrite a valid criterion merely to get a pass.

Run `make scenarios` to check catalog and contract mechanics offline. Run one selected paid case with:

```bash
uv run pytest tests/test_user_scenarios.py -k ambiguous-persistence --run-live -s
```

`make scenarios-live` enables all five paid scenarios. Each runs the real agent and, if structural checks pass, the judge. The user-session test has a shared module event loop for shared agent clients. Calls retain the existing request limits, usage capture and agent/judge cost labels. Outputs and failures save under `outputs/scenario_runs/<case_id>/<run_id>/result.json`.

Deterministic checks verify references point to known opened reports, off-topic response fields meet their contract, and requested Python parses as syntax without executing it. The judge handles semantic expectations, formatting style, contextual adaptation and installation wording. A passing verdict is not source-grounded correctness or analyst approval; use the existing evidence-based tests for that.
