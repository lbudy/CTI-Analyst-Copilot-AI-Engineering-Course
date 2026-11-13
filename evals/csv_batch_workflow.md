# Course CSV batch running — Section 31

`questions.csv` is the runnable 27-question CTI catalog with precisely question,group,type columns. `questions_course_reference.csv` preserves the original 27 Evidently questions supplied by the user. The reference file does not change the application's CTI index. Live default collection uses CTI questions; Section 30 continues to define the reviewed case metadata and calibration/holdout split. Keep JSON case metadata and CSV questions synchronized; a regression test verifies exact question order.

The notebook Section 31 shows pandas loading, first-question inspection, the actual runner implementation, tqdm batch progress, normalized calls, explicit token/cached-token cost estimates, failure handling and combined JSON output. `evals.batch` is the reusable implementation. It uses the application's AgentStreamRunner with a silent JSONParserHandler. Existing course helpers extract tool calls and identify actual executed models for pricing. The price table has an explicit verification date; unknown models remain unpriced. Error rows retain known usage when the runner provides it; provider usage unavailable on interrupted calls cannot be reconstructed or treated as free.

A batch checkpoints one JSON list after each question, so failures do not discard successful rows. Existing filenames are rejected to preserve prior runs. Each result contains input, rag_response, tools, cost, status, turn usage, messages, latency and trace context. Cost includes setup turns for the three multi-turn CTI cases. The separate first-question demonstration is outside batch totals. If any request is unpriced or interrupted, total_estimated_usd is null and known_estimated_usd is a lower bound on captured estimated costs, not an invoice. Costs do not include analyst labor, monitoring charges or non-token fees.

Run:

```bash
uv run python -m evals.batch
uv run pytest tests/test_batch_evaluation.py -q
# Paid agent calls, genuine full batch:
uv run python -m evals.batch --run-live
```

Outputs save under outputs/evals_run_<UTC timestamp>.json and a summary file. The notebook also bridges the course-shaped batch outputs into Section 30's existing response-bound human label files. Review the exact evidence and fill reviewer/good/rationale manually. Labels are never inferred from confidence, self-checks, feedback or the judge. True human labeling cannot be completed automatically by the assistant; no gold-standard or measured quality claim is made until those reviews exist.

The CLI allows selecting another CSV via --csv, but custom questions require corresponding reviewed case metadata for conversion into the gold-label workflow. The original course loop treats its two follow-up rows independently; this project supplies genuine setup history for the three explicit CTI multi-turn cases. Section 32 implements both optional course progress-map snippets. The agent batch uses bounded asyncio concurrency (default 4); use --max-concurrency 1 for sequential runs.

## Bounded parallel execution (Section 32)

`evals/parallel.py` contains both supplied patterns: async_map_progress (Semaphore/as_completed, completion order) and threaded_map_progress (caller-owned ThreadPoolExecutor, submission order). Each has a progress toggle for tests. On failure/cancellation the async helper cancels and awaits unfinished tasks; thread mapping cancels queued work and waits for running tasks before closing progress. The supplied executor stays reusable.

run_batch uses async mapping with max_concurrency=4. It creates independent per-case history/parser and session contexts on one event loop; multi-turn setup remains sequential. Only the parent completion consumer writes checkpoints, ordering output by positional row_index. Concurrent workers do not write the JSON file. Case failures remain recorded without stopping the other cases. A fatal checkpoint error cancels outstanding tasks.

Use `uv run python -m evals.batch --run-live --max-concurrency 4`. Lower to 2 or 1 when rate limits or latency warrant. Simultaneous cases are bounded; this is not an API requests-per-minute limiter. Neither helper adds retries or promises a linear speed increase. Thread mapping is demonstrated for synchronous anonymization, not for sharing an async provider client across event loops. No paid speed benchmark was run.
