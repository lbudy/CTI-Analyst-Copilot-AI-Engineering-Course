# Human-aligned quality evaluation (notebook Section 30)

The course framework is adapted to CTI reports rather than Evidently documentation. `evals/data/quality_cases.json` contains 27 candidate questions across nine equivalence partitions. Three questions per partition vary phrasing, domain context and unsupported assumptions. Three multi-turn cases include a genuine preceding question. Review the catalog for representativeness before treating it as an evaluation set.

Run the cells in the existing `notebooks/02-rag-chemical-triage.ipynb`, Section 30:

1. Inspect questions and the explicit correctness rubric. The catalog is a proposed evaluation set, not manually labeled gold.
2. Enable `RUN_QUALITY_COLLECTION` to make paid agent requests. The API key must be configured. All 27 targets plus three setup turns are attempted. Each case saves its own run immediately under `outputs/quality/<batch>/runs/`. Messages preserve tool calls and returns. Usage is provider-reported; failed in-flight requests can have unavailable usage. Logfire traces require the write token, but local saving does not.
3. Review the reports, exact responses and actual tool evidence. Edit `human_labels.json`: reviewer, strict boolean good, rationale and failure tags. Null labels are intentionally invalid. Each label names the saved response hash; altering the run invalidates it. User feedback is useful for sampling but not automatically a gold label. Execution errors count in the all-attempt metric and are reviewed separately.
4. Enable `RUN_CALIBRATION_JUDGE` after labeling. The separate tool-free judge sees the question, output and evidence, never your verdict. Compare disagreements on 18 calibration questions. Save and version any rubric changes; each judge record stores a rubric hash, model and tokens. Do not silently redefine correctness merely to improve agreement.
5. Freeze the rubric and enable `RUN_HOLDOUT_JUDGE` for nine held-out questions. Do not tune on these results. The notebook enforces complete response labels/predictions for the selected split; analysts remain responsible for keeping holdout labels unseen during tuning.
6. Inspect human quality, execution errors, confusion counts, judge agreement, false acceptances and failure tags. Change the agent based on calibration evidence, collect a new batch and compare with fresh response-specific human labels. Keep earlier batches.

Questions were authored with AI assistance and adapted to the local corpus; their expected behavior is not a reference answer or verified finding. Related phrasings share partitions, so this small split measures sampled behavior, not broad generalization. Report sample sizes, model/rubric versions and uncertainty. Zero-denominator metrics are null. Schema validity and positive self-checks do not establish truth. Existing risk weights, PIRs, triage approvals, retrieval evaluation and earlier judges remain intact.

The current workflow saves judge results one completed batch at a time; a provider failure can interrupt judging. Saved collection outputs remain available for rerun. Inspect model usage records before assuming an interrupted request was free. Full trace evidence is retained locally for evaluation, so these generated files stay under the gitignored outputs directory.

Offline checks: `uv run pytest tests/test_quality_evaluation.py -q`. Paid switches default false; there are no measured quality or alignment results until you run collection and supply human labels.
