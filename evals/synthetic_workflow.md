# Persona-based synthetic evaluation — Section 36

The existing main notebook now follows the course's source-first generation lesson using local threat reports. `evals/synthetic.py` adds GeneratedQuestion, QuestionsResponse and GeneratedQuestions; add_line_numbers/create_user_prompt; a Pydantic AI data_generator; bulk generation and flattening to questions_generated.csv; and agent/reference-aware judge evaluation. The earlier `evals/evaluation.py` synthetic primitive is retained.

Run Section 36 cells in order. Three switches independently control paid calls: RUN_ONE_SYNTHETIC_DOCUMENT, RUN_BULK_SYNTHETIC_GENERATION and RUN_SYNTHETIC_AGENT_EVALUATION. They default false. No generated candidate dataset or measured synthetic score is claimed until live generation/evaluation runs. API keys load from the existing .env without printing them.

Filter source reports to more than 1,000 characters and skip changelog inputs. Estimate one question per 1,000 characters, capped at 16/report for long advisories. The notebook prints the corpus-specific planned count; this is not a guarantee of 200 questions. The generation model uses frustrated_beginner, hurried_developer (hurried analyst), context_assumer and direct_inquirer styles, while questions must remain standalone and supported by the source.

Questions carry a reference answer and inclusive report-text line range. Output validators enforce count, distinct questions, ordered/in-bounds lines and a nonempty support range. Host code sets exact filename, original source URL/hash and extracts the passage without asking the model to invent metadata. Bulk generation checkpoints successful document outputs, known usage and failures, then saves flattened CSV/JSON and removes duplicate question text. Interrupted provider calls may incur costs absent from returned usage.

These validations establish traceability, not semantic truth. Review reference coverage, realism, source interpretation, exact indicators/commands, historical caveats and duplication. All new rows have analyst_reviewed=false. Generated reference answers are not known-correct human gold. Same-model generator/judge biases can make apparent agreement misleading; retain independent source review and the separate manual holdout dataset.

For evaluation load the JSON candidate archive. The code checks source hashes and exact stored passages before paid calls, runs the existing bounded-concurrency agent batch without giving it reference answers, then adds synthetic references and support for the tool-free log judge. The judge compares substantive coverage and grounding rather than exact wording, treating the source as authoritative if the generated answer is wrong. Original agent messages, calls and usage remain saved. Agent/judge errors are distinct and classification coverage is reported alongside judge-good/all-attempts. No analyst gate, risk weight or PIR is changed.

Saved directories: outputs/synthetic/<batch>/ for generated_documents.json, generation_usage/errors, questions_generated.csv/json; outputs/synthetic_evaluations/<batch>/ for agent results, judge JSON/CSV and summary. Source line numbers refer to the full extracted local text, not PDF pages or original website lines. Use source_url for provenance and the text snapshot/hash for reproducibility.

Offline tests: `uv run pytest tests/test_synthetic_course.py tests/test_log_judge.py -q`. These verify line provenance, source drift, persona structure, bounded counts and that reference answers are withheld from the evaluated agent. No live generation or quality score is claimed by tests.

## Agent-only CSV collection — Section 37

The course's separate collection step is `evals/run_evals_synthetic.py`. It accepts --questions, --output, --limit, --concurrency (default 5), --model and --run-live. A generated CSV is required; the default evals/questions_generated.csv is a convenience, while the actual Section 36 output path should normally be passed explicitly. Relative paths resolve from the repository root.

```bash
uv run python evals/run_evals_synthetic.py --questions outputs/synthetic/BATCH/questions_generated.csv --limit 10 --concurrency 5 --run-live
```

Each concurrent task creates its own agent and runner/history, sharing only cached read-only search tools. Only the question reaches the agent; the full CSV row, including reference answer, is kept in saved input. No judge runs. A single completion consumer checkpoints dated _synthetic.json output in CSV order; prior filenames are rejected. Errors are retained and do not stop other questions. Costs include available interrupted usage, unknown totals remain null, and the summary reports CostAccumulator token totals, elapsed wall time and errors. Provider failures may cost money without returning usage. The supplied course's cost and timing are not measured results for this project.

Offline tests cover CSV/limit handling, fresh agents with shared tools, preserving references, error continuation and saved output/cost summaries. No live synthetic batch has been run by implementing this lesson.
