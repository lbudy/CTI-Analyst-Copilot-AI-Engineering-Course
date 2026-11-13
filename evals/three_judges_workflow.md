# Focused synthetic judges and explorer (Section 38)

Three separate tool-free Pydantic AI judges evaluate the saved Section 37 agent results:

- Answer correctness: semantic coverage of the generated reference, using the source passage and retrieved evidence as authority. Equivalent wording/code is allowed; an unsupported generated reference is not treated as unquestionable ground truth.
- Instruction following: important applicable requirements from captured historical instructions, against actual answer/structured fields/messages. Self-checks do not prove compliance.
- Trajectory optimality: demonstrably redundant or irrelevant search/file calls, with a concrete suggestion. Three searches are a review signal, not automatic failure; cross-report questions can justify refinement. Efficiency does not replace correctness.

```bash
uv run python evals/run_judge_checks.py --data outputs/YOUR_RUN_synthetic.json
# Paid judge calls only (up to 3 per completed entry):
uv run python evals/run_judge_checks.py --data outputs/YOUR_RUN_synthetic.json --concurrency 5 --run-live
uv run --extra ui streamlit run evals/explore_judge_results.py --server.port 8503
```

Relative paths resolve from the repository root. Without --run-live the CLI only loads the file. The shared Semaphore caps actual judge requests across entries/dimensions, not five entries each launching an unbounded group of requests. Each completion is checkpointed by one parent writer to a new dated _judged.json. The _summary.json reports good/bad/unclassified counts, all-entry and classified-only good percentages, known cost estimates and whether costs are complete. The manifest records input/rubric hashes, model and concurrency. Each verdict stores known usage, actual provider model, cached-token-aware cost estimate and elapsed time. Provider failures can incur unreported charges.

Judge errors have status error and null score; unavailable historical prompts/reference answers/trajectories have status missing and null score. Neither is silently labeled bad. No completed agent response means all dimensions remain missing. No live quality/cost/timing score is claimed as part of implementation. Missing evidence still limits the reliability of completed judge verdicts.

Section 31/37 default collection now stores its configured system_instructions in new records. Older files are not retroactively relabeled with the current prompt. Captured message system prompts are also recognized. The explorer explicitly states when historical instructions are missing. No current-prompt fallback is substituted.

The Streamlit explorer recursively finds *_judged.json under the selected directory (default outputs). Filters combine across three dimensions and distinguish good/bad/error/missing. Browse question/reference/source line range, agent answer, original CTI source links, unknown-safe cost metadata, self-checks, follow-ups, tool sequence, retrieved messages, all judge explanations, efficiency suggestions, usage and historical instructions. No model calls are made while browsing. Open port 8503 in Codespaces. CTI_JUDGED_DIR can set the initial directory.

This is still a research evaluator: generated references and judge conclusions are fallible; historical report evidence is not proof of present company compromise or analyst approval. Preserve independent human labels and the held-out judge-validation workflow. Compare rubric/model versions before interpreting changed scores. The supplied course's reported $0.16/200 cases is not a result for this project.
