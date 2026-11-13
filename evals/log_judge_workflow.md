# Course LLM log judge (Section 34)

`llm_judge.py` provides JudgeEvaluation(reasoning, label), create_log_judge_agent and format_judge_prompt. `evaluate_judge.py` loads the labeling app's _results.json, calls the tool-free judge and compares verdicts with human correctness labels. The course is adapted to CTI reporting rather than Evidently docs. Its formatting/Evidently Cloud requirements and illustrative metrics are not imported as CTI correctness rules.

The prompt allowlists question, structured response, tool calls, evidence messages, execution status and actually captured system instructions. Human label/comments/reviewer are never sent. It treats payloads as untrusted, checks actual evidence and does not accept confidence/self-checks as proof. Judge output places the concise evidence-based reasoning field before label. This schema order is not a guarantee of model accuracy.

```bash
# Validate the labeled file without paid calls:
uv run python evals/evaluate_judge.py --data outputs/YOUR_BATCH_results.json
# Paid calibration (default split):
uv run python evals/evaluate_judge.py --data outputs/YOUR_BATCH_results.json --run-live
# After freezing the rubric, a paid held-out run:
uv run python evals/evaluate_judge.py --data outputs/YOUR_BATCH_results.json --split holdout --run-live
```

Relative --data paths resolve from the repository root, independent of the shell's current directory. The file must contain nonempty labeled results and labels must be good/bad. Default CTI catalog partition metadata selects calibration/holdout. Custom questions require reviewed split metadata, or explicitly choose --split all and disclose that there is no independent holdout. Any self-selected representative subset should be documented; the script cannot establish that a file covers all intended questions.

The script checkpoints completed predictions after each row to a uniquely dated JSON file, writes _evaluated.csv and .metrics.json, prints a confusion matrix and disagreement table. Each successful prediction stores actual model, input/output/cache usage, dated-price token estimate, rubric hash, source hash and latency. Failed calls may incur unreported provider charges. Errors retain null predictions and are counted separately; unlike the pasted fallback, they are not silently treated as valid bad verdicts. Agent execution errors are excluded from completed-response agreement and remain explicit rows.

Bad is the positive class. Accuracy = (TP+TN)/compared, precision = TP/(TP+FP), recall = TP/(TP+FN). A zero denominator is null. Attempted/compared/excluded and judge_errors counts prevent errors and missing predictions from silently inflating agreement. Disagreement reporting uses valid human/predicted labels only. No score is claimed until actual reviewed data and live judge results exist.

Use calibration disagreements to refine general rules, inspect whether the human label is justified and version changes. Do not encode exact questions or tune on held-out outcomes. A stricter judge may improve bad-class recall while reducing precision; measure both. The independent source-evidence checks and analyst approval gates remain necessary.

No live dataset evaluation was performed as part of implementation. Offline tests verify prompt-label isolation, no research tools, output schema ordering, the course's 60%/50%/50% toy confusion example, undefined denominators and continued processing after judge errors.
