# Course evaluation exercises

The notebook's section 17 is the walkthrough. Project functions live in `evaluation.py`.

1. Run the deterministic test suite. Real provider calls are disabled in fake-model tests.
2. Run the 13-query title-based retrieval smoke set to check corpus coverage. This is not a realistic held-out benchmark.
3. Enable synthetic generation explicitly to generate one question per report. Validate exact quotations, inspect reference answers, remove ambiguous or trivial questions and mark reviewed cases honestly. Add difficult multi-report and unanswerable questions manually before claiming real quality. The present `EvalCase` requires at least one reference report; a pure unanswerable benchmark needs its own schema/metric.
4. Split reviewed questions into development and held-out evaluation sets before tuning prompts or retrieval.
5. Run agent and judge evaluations explicitly. Both consume model tokens. The judge gets expected reports as evidence and produces 0–4 groundedness, correctness, relevance and citation-quality ratings. It does not verify the analyst's organizational assumptions or the full corpus exhaustively.
6. Compare judge ratings with analyst ratings, including deliberately unsupported and incomplete answers, before choosing thresholds. Do not use the agent's confidence as correctness or judge scores as publication approval.
7. Inspect JSON artifacts for individual failures. They include corpus digest, model identifiers, separate agent/judge token usage and latencies. Optionally pass `agent_prices=TokenPrices(...)` and `judge_prices=TokenPrices(...)` to `evaluate_answers` using verified current prices; absent prices produce `null` cost, not zero.
8. Install `uv sync --extra evaluation` and call `evidently_report` for an HTML summary. It summarizes recorded scores; no additional LLM requests occur. It is not a calibrated quality gate.

Failures are raised rather than silently treated as successes. Completed runs record their usage; exceptions before a result is returned may still incur provider charges not represented by a completed-run artifact. Keep provider billing records for reconciliation.

Optional graph streaming uses public node predicates and jaxn to display provisional fields. Final output is accepted only after the graph completes and Pydantic validates it. Live execution remains bounded at six requests and ten tool calls by default.
