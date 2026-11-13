# Run agent + judge quality evaluation (Section 35)

`evals/run_evals.py` combines CSV batch collection, the existing log judge, and a saved quality/cost/time report. It is the course pipeline adapted to CTI reports; it does not assume the judge has already been shown aligned with this project's human labels.

```bash
uv run python evals/run_evals.py
uv run python evals/run_evals.py --run-live --max-concurrency 4
uv run python evals/run_evals.py --run-live --compare outputs/evaluations/PRIOR/evaluation_report.json
```

Without --run-live it loads the question catalog and prints the plan without paid requests. With it, phase 1 runs 27 CTI question cases (plus genuine setup turns for multi-turn cases) using the existing bounded async batch. Phase 2 judges completed responses sequentially using the same evidence-aware prompt as evaluate_judge.py. Phase 3 saves a summary and merged per-question results. Agent and judge models are independent CLI options. No live pipeline run is claimed by implementation tests.

Each uniquely named outputs/evaluations directory contains manifest.json, checkpointed agent_results.json, checkpointed judge_results.json, judge_results.csv and evaluation_report.json. Per-question records retain the actual response, research tools, messages, usage, cost and latency. Tool trajectories exclude final_result and include all setup/follow-up research calls. A configurable count above six is flagged for investigation, not automatically labeled incorrect. No early-stop prompt or analyst gate is changed by this lesson.

The report distinguishes good/bad verdicts from agent/judge errors. Primary good_pct_all_attempts uses every attempted question as its denominator; good_pct_classified and coverage are reported alongside it. Judge failures are never replaced by bad labels. A missing classification is therefore visible, rather than silently counted as a real verdict or removed from the main denominator. Judge-estimated quality is not a gold-standard correctness rate.

CostAccumulator tracks agent and judge input/output/cached tokens and known token-cost estimates separately. Unknown rates or unavailable error usage make total cost null; known cost is a partial estimate, not billing reconciliation. Successfully observed interrupted-agent usage remains in the existing batch records. Phase wall-clock durations include concurrent agent work correctly; per-case latency sums are not mislabeled as wall time. Logfire/export charges, taxes and other non-token costs are excluded.

Comparison requires identical question, judge-rubric/model and corpus hashes. The manifest also records prompt/settings and agent/retrieval code hashes, allowing interventions to be inspected. Save new batches for each change. Record coverage/errors and paired failures, repeat runs to assess variation and preserve held-out judge-validation data. A percentage increase from a fallible stochastic judge does not automatically prove improvement; do not blindly keep/revert based on that number alone.

The existing calibration/holdout and human-labeling apps remain the path for demonstrating judge alignment. The course's historical quality results are not results for this project. The report is research evaluation, not approval to process or distribute intelligence.
