# CTI Analyst Copilot

AI-Assisted Threat Information Triage, Research, and Intelligence Analysis



## The Problem

Cyber Threat Intelligence (CTI) analysts receive large volumes of external threat reports from vendors, security researchers, government sources, ISACs, and other intelligence sources. These reports contain potentially valuable threat information, but they are not yet organization-specific intelligence.

Analysts must determine which reports are relevant to their organization, extract important threat data, investigate and enrich artifacts across multiple tools, and correlate the resulting evidence before they can focus on deeper analysis and produce finished intelligence.

This process is often manual, fragmented, and time-consuming. Analysts may need to move between threat intelligence platforms, external enrichment services, and internal security telemetry while processing a single report.

The CTI Analyst Copilot aims to reduce this processing and research burden so analysts can spend more time on intelligence analysis and support teams such as Incident Response, Detection Engineering, and Threat Hunting.

## What It Does

The CTI Analyst Copilot assists analysts through several stages of the threat intelligence workflow.

1. Relevance Assessment

The system evaluates incoming threat reports against predefined organizational context, including:

Priority Intelligence Requirements (PIRs)

Intelligence requirements

Technology exposure

Industry and sector

Geographic exposure

Threat actor priorities

Risk and relevance criteria

It returns an explainable relevance assessment indicating whether the report warrants further analyst attention and why.

2. Threat Information Processing

For relevant reports, the system uses structured LLM outputs to identify and organize important data points such as:

Threat actors and campaigns

Malware

Vulnerabilities and CVEs

MITRE ATT&CK TTPs

Domains, IP addresses, URLs, and file hashes

Adversary infrastructure

Victimology and targeting information

Potential detection opportunities

Potential threat-hunting opportunities

The goal is to transform unstructured reporting into structured threat information that can support further investigation.

3. Artifact Research and Enrichment

Analysts can select extracted artifacts for further investigation.

An agentic workflow can query external threat intelligence sources such as VirusTotal and other enrichment services to gather additional evidence and identify relationships or useful investigative pivots.

The system can also search internal SIEM telemetry to determine whether indicators or related activity from the report have been observed within the organization's environment.

4. Evidence Correlation and Analysis Support

The system combines the original report, extracted threat information, external enrichment, internal telemetry, and relevant organizational context to provide the analyst with an evidence-supported view of the threat.

This can help identify:

Relevant internal activity

Relationships between indicators and infrastructure

Detection opportunities

Threat-hunting opportunities

Potential intelligence gaps

Areas requiring deeper investigation

The system can assist in preparing an initial analytical assessment, but the analyst remains responsible for validating the evidence, applying analytical judgment, determining confidence, and producing the final intelligence product.

Core Principle: Information Is Not Intelligence

A key design principle of this project is maintaining the distinction between collected threat information and finished intelligence.

External reports, indicators, TTPs, enrichment results, and SIEM hits are treated as information and evidence. They become organization-specific intelligence only after they have been evaluated, contextualized, analyzed, and assessed against the organization's intelligence requirements.

The CTI Analyst Copilot therefore aims to assist the intelligence lifecycle rather than replace the intelligence analyst.

## Setup

1. Install uv if you don't have it yet: https://docs.astral.sh/uv/getting-started/installation/

2. Clone this repository (or download the zip and extract it).

3. Create a `.env` file from the template and add your API key:

       cp .env.example .env

4. Install dependencies:

       uv sync

5. Start Jupyter:

       uv run jupyter notebook

## Notebooks

- `notebooks/01-setup.ipynb` - smoke test that confirms your environment works
- `notebooks/02-rag.ipynb` - a minimal RAG baseline you can adapt to your own data

## Data

Put your project data in the `data/` folder. See `notebooks/02-rag.ipynb` for how to load it.

## Implemented course baseline

`notebooks/02-rag.ipynb` retains the local CISA corpus, 3,000-character chunks with
500-character overlap, MinSearch TF-IDF retrieval of five passages, and the
`search → build_prompt → llm → rag` question-answering pipeline.

The notebook contains the complete analyst-reviewed workflow code, company profile,
PIRs, and matrix inline. `cti_workflow.py` remains a companion implementation for
standalone use and tests; the notebook does not import it. The workflow supports:

1. Inspect the fictional German chemical company, 17 PIRs, and weighted matrix.
2. Explicitly enable `RUN_TRIAGE` to assess every complete report independently.
3. Review cited criterion assessments, PIR mappings, score ranges, confidence,
   evidence coverage, gaps, escalation flags, and visible failures.
4. Record approve/defer/reject decisions, reasons, and optional priority overrides.
5. Explicitly process approved reports into Pydantic-validated summaries, entities,
   technical evidence, and proposed IR/hunting/detection actions.
6. Approve the processed output separately before exporting a local JSON handoff.

The saved unreviewed queue reloads by default. Set `LOAD_SAVED_TRIAGE = False`
in section 6 to make fresh paid triage calls. Token usage is captured for triage
and processing. Audit
records and exports live in gitignored `outputs/`. The baseline trusts the person
running the notebook; analyst identities are entered manually, not authenticated.
Exact quotations are checked, but semantic interpretation still requires review.
SIEM connectors, enrichment services, and automatic distribution are not implemented.

Offline verification: `uv run python -m unittest discover -s tests -v`.

## Agentic RAG — following the course

Use `notebooks/02-rag-chemical-triage.ipynb` as the main project notebook.
All lessons and implementation code remain inside it:

- **Section 10:** manually inspect one tool call, execute retrieval, generate a
  structured answer, check quotations, and inspect tokens.
- **Section 11:** the course's `make_call` and visible `while True` agentic loop.
  Run cells 11a–11f in order. Set `RUN_COURSE_AGENT = True` in 11a to enable paid
  calls. Inspect each iteration, requested query, returned result, history, and
  token usage. The prompt requests one search, two refined searches, then an
  answer; actual model behavior can vary.
- **Section 12:** the optional `add_entry` exercise, using the same loop with two
  tools. Enable `RUN_COURSE_ADD_ENTRY` only after completing section 11. Generated
  notes go to an in-memory scratch index and are labeled as generated, unreviewed
  notes. They do not change public reports or the production search index.
- **Section 13:** the course's outer Q&A loop wrapped around the inner tool-call
  loop. Run prerequisites 11a–11d and 12a–12b; enable `RUN_COURSE_QNA` in 13a.
  Ask questions at `You:` and type `stop` to exit. History persists across turns.
- **Section 14:** the course-style `Agent` library, with `__init__`, `make_call`,
  `loop`, and `qna`. The entire class is inline and also available in
  `course_agent.py`. Python tool implementations are passed explicitly through
  `tool_functions`, so the library has no dependency on notebook globals.
  Enable `RUN_LIBRARY_SINGLE_QUESTION` or `RUN_LIBRARY_QNA` in 14b, rerun 14b,
  then run 14c or 14d. Both flags default to False.
- **Section 15:** the course's structured-output lesson: `RAGResponse`,
  `SimpleStructuredAgent` (parse every iteration), `StructuredAgent1`
  (normal research loop plus one formatting request), and `StructuredAgent2`
  (`structure_result` pseudo-tool). The implementations are inline and reusable
  from `course_structured_agent.py`. Enable one flag in 15e, rerun 15e, and run
  the corresponding 15f/15g/15h example. Optional structured Q&A is in 15i.
  All flags default to False. The base Agent and earlier course lessons remain.
- **Section 16:** Pydantic AI framework migration, following the course's typed
  SearchTools, docstring schemas, full-report search, Agent creation, async runs,
  message inspection, follow-ups, Q&A, RunUsage, and NamedCallback event handler.
  Optional native structured output reuses RAGResponse. All framework exercise
  flags in 16a default to False. This is the next framework lesson, not a rewrite
  of the earlier manual loops.
- **Optional reference before section 16:** the earlier custom structured agent,
  retained for comparison. It is not needed to complete the course lesson. `cti_agent.py` is its
  standalone counterpart.

Sections 11–12 follow the supplied course example directly: model request →
`message_history.extend(response.output)` → `make_call` → append
`function_call_output` → repeat until no calls remain. An iteration cap and token
logging are explicit additions. The course loop produces free-text output, not
section 10's Pydantic-validated answer; its claims and citations need analyst review.

A learning tracker inside section 12 maps each course concept to its code,
project adaptation, and verification status. Live exercise calls are disabled by
default. All scoring and analyst approval gates remain separate and unchanged.

Offline tests: `uv run python -m unittest discover -s tests -v`.
API reference: https://developers.openai.com/api/docs/guides/function-calling

Q&A and library tests use scripted inputs and model responses, without API calls.
They check follow-up context, matching tool-call IDs, stop handling, instance-specific
instructions, independent agent state, iteration limits, and token accounting.
Interactive research outputs remain unreviewed; the existing analyst gates are
unchanged. The class uses only the supplied scratch-index functions.

The structured-output schema follows the course's six fields: answer, found_answer,
confidence, confidence_explanation, answer_type, and followup_questions. Confidence
is constrained to 0–1 but remains an uncalibrated model self-assessment. Valid shape
is not proof of correct threat claims or citations; section 10's quotation checks
and existing analyst review remain separate. The final-result pseudo-tool is
acknowledged in history so follow-up calls stay valid. Both wrapper and pseudo-tool
Q&A are tested offline; no live model behavior is assumed from scripted tests.

## Expanded report corpus

The corpus now includes 13 reports: the original three CISA snapshots plus ten
additional joint advisories downloaded as original PDFs from FBI IC3. Local PDFs,
extracted text, hashes, page offsets, source URLs, and dates are documented in
`data/README.md` and `data/source_reports/manifest.json`. The notebook reads the
same `data/threat_reports.json`, now producing 242 chunks. Reload its loading and
indexing cells after a corpus update. New reports are not automatically scored.

Offline PDF ingestion: `uv run python scripts/ingest_report_pdfs.py`.
This uses pypdf, not MarkItDown. No live feeds or OCR are implemented.

The report-loading and indexing cells apply the same core contract and chunking
strategy to all original and PDF reports. The indexing output includes a report-by-
report pipeline audit. Offline integration checks cover top-five retrieval, prompt
construction, the original `rag` chain with a stub LLM, readable citations, and
compatibility with existing structured records and analyst approval gates.

## Pydantic AI course framework lesson

Run sections 1–2 to load the corpus, then follow section 16's cells in order.
The lesson indexes 13 full reports separately from the original 242-chunk index.
`SearchTools.search` returns MinSearch highlighted snippets; `get_file` returns
exact complete extracted report text by filename. Typed Google-style docstrings
supply tool schemas automatically. A local `get_instance_methods` mirrors the
course helper without adding ToyAIKit. `pydantic_search_tools.py` contains the
same definitions for reuse; the notebook keeps all code inline.

Pydantic AI is imported as `PydanticAgent` to preserve the earlier course `Agent`.
The configured model remains `openai:gpt-4o-mini`. Set the appropriate live flag
in 16a and then run the question, follow-up, Q&A, streaming, or structured-output
cell. Jupyter supports the shown top-level `await`; do not wrap these cells in
`asyncio.run()`. Tools are read-only and restricted to the report mapping.
No note writing, approvals, scoring changes, SIEM access, or exports are exposed.

The lockfile installs Pydantic AI 1.107.10 via `pydantic-ai-slim[openai]`. Its
`result.usage` property replaces the older course's `result.usage()` spelling.
Request/tool-call limits bound each run. Usage aggregation follows the course;
totals shown in the notebook include completed runs, not interrupted runs that
return no result. The project is still a prototype, not a production deployment.

Offline tests use Pydantic AI FunctionModel with real provider requests disabled.
They exercise search/open/answer, generated schemas, history, Q&A, usage, output
validation, and native event streaming. Some execution sandboxes block asyncio's
worker-thread wakeup socket; those environments need the test runner's local
communication permission, without enabling any live model request.

References: https://pydantic.dev/docs/ai/core-concepts/agent/ and
https://pydantic.dev/docs/ai/tools-toolsets/tools/.

### Course event-stream handler (16k)

The event lesson has separate cells for defining `NamedCallback`, creating the
callback/query, viewing a labeled scripted preview, calling
`await search_agent.run(..., event_stream_handler=callback)`, and inspecting the
actual live trace/messages. The preview does not call a model or any tools and
uses its own callback to avoid mixing synthetic events with live evidence.
Enable `RUN_PYDANTIC_STREAM` in 16a for the paid live example, then run 16k.1–16k.5.
Existing tool-return and text-delta tracing remain available alongside the
course's tool-call printer. Each live rerun clears its previous event trace.

## Course testing and evaluation project

Section **17** of `notebooks/02-rag-chemical-triage.ipynb` follows the next course module. It preserves sections 1–16 and adds visible source inspection and runnable exercises. Sections 17g and 17h run live generation and evaluation directly when executed; 17j is an optional live streaming example. They no longer depend on enable flags. Each completed candidate and evaluation is displayed and saved. Offline tests skip these explicitly tagged live cells.

- `tools.py`: validated local corpus, full-report index, content-keyed memory cache; reuses existing read-only tools.
- `doc_agent.py`: `DocumentationAgentConfig`, `create_agent`, bounded `run_agent`, graph-based `run_agent_stream` and the existing structured response schema (`models.py`).
- `main.py`: one-question CLI or interactive Q&A, preserving the actual user question and conversation history.
- `cost_tracker.py`: explicit per-million rates, cached token handling; example notebook rates are arithmetic fixtures, not current provider prices.
- `evals/evaluation.py`: hit rate@k/MRR@k, exact-evidence validation, live synthetic candidates, structured LLM judge, separate agent/judge usage, latency and JSON artifacts.
- `evals/data/retrieval_smoke.json`: one title query per report. This checks all 13 reports are searchable; it is not a held-out semantic benchmark.
- `structured_stream.py`, `app.py`: optional jaxn partial-field display and Streamlit research interface. Partial content is provisional; final output is validated. Neither approves reports nor publishes intelligence.

```bash
uv sync --dev
uv run pytest -q
uv run python main.py --question "What does Akira target?"
uv run python main.py --question "What does Akira target?" --stream
uv run --extra ui streamlit run app.py
uv sync --extra evaluation
```

Tests use Pydantic AI FunctionModel and disable real provider requests. Live CLI/UI questions and synthetic/judge exercises need an API key and incur usage. Generated evaluation candidates remain unreviewed; check their evidence, expected answer, and difficulty, keep a held-out set, and compare judge ratings with analyst ratings before adopting thresholds. Evaluation does not override the risk matrix or analyst approval gates. Evidently creates a local HTML summary of recorded scores and latency without making additional judge calls. The existing ingestion and chunk-based RAG remain unchanged.

## Course text-streaming lesson

Section **18** in the same notebook follows the course's `run_stream()` comparison and graph-based text streaming. Functions are shown in editable notebook cells and also live in `doc_agent.py`:

- `run_agent_stream_simple`: text deltas with the course callback. First matching text can end a simple stream before later tool work; use it as a comparison.
- `print_stream_node`, `print_tool_calls`: focused helpers for model text and observable tool calls.
- `run_agent_stream_text`: graph iteration through tool execution, returning the completed result with final text, messages and usage.

The agent factory still defaults to `RAGResponse`; the lesson selects `output_type=str`. Existing structured graph streaming and Streamlit remain available. Section 18e is an offline fake-model demonstration. Sections 18f–18h are explicitly labeled live calls, with no enable flags; run only the examples you want. They use the same 13-report corpus and preserve approval gates.

```bash
uv run python main.py --question "Akira VMware evidence" --stream-mode text
uv run python main.py --question "Akira VMware evidence" --stream-mode simple
uv run python main.py --question "Akira VMware evidence" --stream
uv run pytest tests/test_pydantic_streaming.py -q
```

## Streamlit chat application

`app.py` wraps the existing agent without modifying its code. Do **not** rename it `streamlit.py`, which would shadow the Streamlit library.

```bash
uv run --extra ui streamlit run app.py
```

The sidebar links to `lbudy/CTI-Analyst-Copilot-AI-Engineering-Course`. This project searches local CTI reports, not the course's Evidently documentation corpus; file-read links therefore open each report's original advisory URL. The app streams structured answer fields with a cursor, retains chat and expanded activity panels across reruns, displays type/confidence/found metadata, and offers clickable follow-up questions only for the latest answer. Clear conversation resets chat and agent history while retaining the cached session agent and index. Each session reuses its own async loop for successive model calls. Failures retain tool activity and remove unvalidated preview content. Chat submissions make paid model requests.

## Course pytest lesson (Section 19)

The original `tests/test_agent.py` still tests the earlier custom agent. `tests/test_documentation_agent.py` follows the course with our Pydantic AI agent, actual CTI report tools, structured output assertions, recorded search/get_file calls, fixtures and formatting checks. `tests/helpers.py::collect_tools` only inspects messages. It never chooses or runs tools.

```bash
uv sync --dev
uv run pytest tests/test_documentation_agent.py -q
uv run pytest -q
# Explicit paid provider-backed scenario:
uv run pytest tests/test_documentation_agent.py -m live --run-live -v
```

VS Code testing discovery is configured in `.vscode/settings.json`; `pythonpath = ["."]` is configured in `pyproject.toml`. Regular tests disable real Pydantic AI provider requests. Live-marked tests require `--run-live`. Fake responses test deterministic control flow, not model behavior or factual quality. Code blocks and source references test formatting, not correctness.

Completed course-test results append to `outputs/test_usage.jsonl`. Terminal summaries separate this run from accumulated runs, and offline fixtures from live tokens. Add verified `--input-price`, `--output-price`, and optional `--cached-input-price` values (USD per million tokens) to the live command to estimate costs. Unknown models stay unpriced (null), not zero. Section 22 adds a dated, officially sourced default table for known course models. Usage for a returned result is captured before assertions, including when an assertion fails; provider failures before a result returns can still incur costs absent from this ledger. The ledger is local and gitignored with other outputs.

Course tool-call follow-up (Section 19f): `tests/utils.py` supplies the `ToolCall` dataclass and `collect_tools` function. It inspects recorded message parts, filters `final_result`, and uses the SDK's `args_as_dict()` because stored arguments may be JSON text or dictionaries. The earlier dictionary helper remains compatible with existing tests. `-s` disables pytest capture so printed tool activity and responses are visible.

```bash
uv run pytest tests/test_documentation_agent.py::test_agent_runs -s
uv run pytest tests/test_documentation_agent.py::test_agent_uses_tools -s
uv run pytest tests/test_documentation_agent.py::test_live_agent_runs --run-live -s
```

The live question can legitimately retrieve either Volt Typhoon advisory. Citation assertions therefore require a URL belonging to a report actually opened, rather than forcing one report ID for a broad question. This checks the observed tool sequence and output format; it does not verify each quoted command or analytical claim.

## Fixtures and runner refactoring (Section 20)

`tests/conftest.py` now provides a module-scoped `agent` fixture and prints setup duration once with `-s`. The offline tests temporarily override that same agent's model while retaining real report tools. Each run starts with fresh messages unless history is explicitly passed; the fixture does not cache responses.

`doc_agent.AgentStreamRunner` owns the user, model-request and tool-node methods. It accepts a JSON handler, explicit `verbose` flag, usage-limit config and the existing `on_event` callback. The production `run_agent_stream` function is a thin wrapper, preserving the CLI and Streamlit interface. Terminal runs render fields through the existing RAGResponseHandler. `tests.utils.run_agent_test` injects a no-op JSONParserHandler and `verbose=False` so both answer text and user/tool prints are quiet. No-op JSON handling alone would not suppress separate tool prints.

jaxn is now a core dependency because the structured runner and quiet test helper consume streamed JSON without requiring the optional UI extra. `uv sync --dev` installs it. Earlier text streaming functions remain available for Section 18's comparison. Output parsing resets per model node and call index, including validation retries. Usage tracking and explicit live-test opt-in remain intact.

```bash
uv run pytest tests/test_documentation_agent.py -s
uv run pytest tests/test_stream_runner_refactor.py -q
```

## Source examples and structured references (Section 21)

The new `test_agent_includes_references` was first run against the old schema and failed because `references` did not exist. `models.py` now defines `Reference(file_path, explanation)` and extends the earlier six-field course response with a typed reference list. The old class in `course_structured_agent.py` is unchanged; an empty-list default keeps earlier saved records readable. The existing application model and instructions request exact filenames from reports actually used, with an explanation. Live scenario assertions check reference presence and correspondence with opened files.

Technical examples are adapted to CTI: quote source commands/code in appropriately labeled fences when relevant to the question; do not force Python into reports that contain none, invent commands, or complete truncated source examples. DEFAULT_INSTRUCTIONS is the maintained prompt; SIMPLE_INSTRUCTIONS is only its compatibility alias.

The Streamlit UI displays reference links and explanations as structured items arrive, then preserves the validated list in chat history. Links resolve to the original advisory URL from the local corpus rather than the course's Evidently repository. Unknown filenames never receive invented links. Cached agents from the previous response-schema version are rebuilt. Preview references are cleared if output fails.

```bash
uv run pytest tests/test_documentation_agent.py::test_agent_includes_code_in_answer -s
uv run pytest tests/test_documentation_agent.py::test_agent_includes_references -s
uv run pytest tests/test_response_references.py tests/test_streamlit_app.py -q
```

Offline fixture tests verify typed fields, streaming, UI replay, source-backed snippets and tool/reference correspondence. They do not establish live answer correctness or analytical quality; use explicit provider scenarios and evidence-based review for those.


## Per-model test cost tracking (Section 22)

`tests/cost_tracker.py` follows the course's defaultdict(RunUsage), automatic capture and end-of-session reporting. `run_agent_test` identifies the executed provider/model from the response, captures completed usage before returning, and optionally prints usage with `show_usage=True`. Manual capture calls were removed from course scenarios; duplicate-result guards prevent double accounting. Existing explicit capture remains available to tests bypassing the helper.

`pytest_sessionfinish` reports current-session input/output/cached tokens and estimated USD per model, with a total. The existing JSONL ledger and terminal summary retain per-test/run records and across-run totals. Offline model usage is kept separate and excluded from API costs, including when an agent's configured model still looks like OpenAI under a FunctionModel override. In-memory accumulators reset each pytest invocation; the ledger persists. Old unpriced entries are not silently repriced.

Default standard text rates were checked on **2026-11-12** against official [GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini) and [GPT-4o](https://developers.openai.com/api/docs/models/gpt-4o) pages. The table includes cached-input discounts and explicitly listed snapshot aliases. Unknown models remain unpriced. Existing CLI rate overrides take precedence for that invocation; estimates exclude taxes, non-token fees and account-specific adjustments. Provider failures before a completed result returns may incur charges absent from this tracker. These are estimates, not billing reconciliation.

```bash
uv run pytest tests/test_documentation_agent.py -s
uv run pytest tests/test_cost_tracking.py -q
# Explicit paid model scenario; default table rates applied automatically:
uv run pytest tests/test_documentation_agent.py::test_live_agent_runs --run-live -s
```

## Course LLM-as-a-judge tests (Section 23)

`tests/judge.py` adds the course's `JudgeCriterion`, `JudgeFeedback`, tool-free `create_judge_agent` and `assert_criteria`. The prompt includes the user question, structured answer, normalized tool-call trace and plain-English requirements. Full tool returns are omitted to limit cost; supply source passages for grounding criteria. A judge without source evidence must not infer factual correctness from prose, references or confidence.

Every criterion must be evaluated exactly once. Missing, duplicate or substituted descriptions trigger bounded validation retries; failed verdicts produce a combined assertion message. The judge has no search/file tools, cannot approve intelligence, and remains a fallible model evaluator. The existing 0–4 evaluator in `evals/evaluation.py` is preserved.

`tests/test_judge.py` contains an offline mechanics test and explicit live scenarios for tool usage, off-topic handling and unsupported company-targeting claims. `tests/test_judge_contract.py` covers strict verdicts, complete criterion coverage, retry bounds and prompt/tool constraints. `tests/utils.py::get_model_name` is shared by research and judge capture. The ledger records `usage_role` as agent or judge in addition to provider/model, so equal-model costs still remain attributable. Prior ledger rows stay unchanged.

```bash
make judge
uv run pytest tests/test_judge.py::test_live_agent_uses_tools --run-live -s
uv run pytest tests/test_judge.py::test_live_agent_uses_tools --run-live --judge-model openai:gpt-4o -s
make judge-live
make tests
make run
```

Live commands make paid agent and judge requests. `--agent-model` and `--judge-model` independently select test models; defaults retain the course's gpt-4o-mini. A stronger or different model is not automatically a reliable judge. Compare verdicts with analyst labels and repeat runs before treating them as a quality gate. Preserve deterministic checks for tool order and schema alongside semantic evaluation; inspect failures before changing either the agent or the criteria.

## User-session scenario wishlist (Section 24)

The course's app-testing session is captured as five CTI-adapted cases in `evals/data/user_session_cases.json`: ambiguous persistence terminology, proposed Python formatting, off-topic chess, use of an existing indicator DataFrame and uv dependency instructions. `evals/user_session_testing.md` explains how to turn written/dictated observations into reviewed cases without adding an audio service. These initial cases are expectations, not fabricated observations of successful behavior.

`tests/scenarios.py` validates the catalog and deterministic contracts. `tests/test_user_scenarios.py` parameterizes live agent-plus-judge runs from the catalog. Code is parsed for Python syntax only and never executed. References must name known files opened during the run. Off-topic cases enforce their declared found-answer/confidence/reference contract. The judge evaluates meaning, follow-up relevance, formatting style and adaptation to supplied column names. These tests do not replace source-grounding or analyst review.

```bash
make scenarios
uv run pytest tests/test_user_scenarios.py -k ambiguous-persistence --run-live -s
uv run pytest tests/test_user_scenarios.py -k off-topic-chess --run-live -s
make scenarios-live
```

Default runs validate mechanics and skip the five paid cases. Live runs save answers, calls, verdicts or failures to `outputs/scenario_runs/<case_id>/<run_id>/result.json`; costs use the existing agent/judge ledger. Structural failures stop before a judge call. Formatting rules concern proposed Python analysis code, not verbatim source commands. The current report-grounded agent may decline code generation or package questions; those cases expose a desired capability/scope decision rather than justify inventing report evidence. Section 25 subsequently updates the application instructions and adds self-verification; see the measured iteration notes.

## Fixing judge tests (Section 25)

The main notebook now shows typed `Check` records, response `to_string()` rendering, plain-text judge input, context/package/style instructions, bounded research and per-worker JSONL cost aggregation. Saved six-field responses remain readable. Self-checks are model claims; independent judge and source-evidence checks remain necessary. Agent and judge models can be selected separately with pytest flags.

The latest five-case live run passed **2** and failed **3**, estimated recorded token cost **$0.028994**. These are measured failures, not skipped formatting tests or a claim that the agent is production-ready. See [iteration notes](evals/judge_iteration_notes.md) for remaining issues and reproduction commands.

## Monitoring (Section 26)

Logfire instruments Pydantic AI in the existing Streamlit app and CLI. The app groups turns under a session span and records follow-up clicks and thumbs feedback. Configure your own LOGFIRE_TOKEN in .env; content capture is explicitly controlled by LOGFIRE_INCLUDE_CONTENT. See [setup and trace export](docs/monitoring.md). The main notebook includes visible configuration cells in Section 26. No dashboard connection is verified without your project token.

Section 27 applies the course session-context pattern: `logfire.span`, `get_context` and `attach_context` group question/follow-up runs in one trace; clearing chat immediately captures a fresh context. Offline tests verify real trace and parent span IDs without uploading data.

## Human-aligned evaluation (Section 30)

The same notebook now includes 27 CTI candidate questions across nine equivalence partitions, genuine multi-turn collection with saved evidence, response-bound manual labels, and a tool-free judge evaluated against an 18-case calibration / 9-case holdout split. Reports include human quality, errors, failure tags, agreement and false acceptances. See [workflow](evals/quality_workflow.md). Human labels and measured quality are intentionally not fabricated; collection and judging require explicit paid switches.

## Course CSV batch workflow (Section 31)

Added `evals/questions.csv` (27 CTI questions) and `evals/questions_course_reference.csv` (the original 27 Evidently questions supplied by the user). The notebook now follows pandas loading → AgentStreamRunner → normalized tools and cached-token costs → tqdm batch loop → dated combined JSON and cost summary. Failures remain recorded and collection continues. Saved results can enter Section 30's manual labeling workflow. See [batch instructions](evals/csv_batch_workflow.md). Live calls require explicit switches or `uv run python -m evals.batch --run-live`; no human labels are fabricated.

Section 32 adds both course tqdm progress-map helpers. The CSV agent batch uses bounded asyncio concurrency (default 4), isolated case histories/traces and a single checkpoint writer; output stays in CSV order. Use `--max-concurrency 1` for sequential execution. The thread-pool example supports synchronous tasks with a reusable executor. Offline tests cover bounds, ordering, cancellation and continued batch collection; no live speedup is claimed.

## Human review UI (Section 33)

Run `uv run --extra ui streamlit run evals/label_evals.py --server.port 8502` to inspect saved responses, source links, tool evidence and instructions, then label Good/Not Good with reviewer/comments. Progress saves separately to _results.json and resumes on restart. The app advances to the next unlabeled run and exports compatible human labels for the existing judge workflow. See [labeling instructions](evals/labeling_workflow.md). No labels or measured quality are fabricated.

## Course log judge and alignment (Section 34)

`evals/llm_judge.py` adds reasoning-first good/bad verdicts. `evals/evaluate_judge.py` evaluates labeled _results.json files, prints accuracy/precision/recall for bad responses, confusion counts and disagreements, and saves checkpoint JSON plus detailed CSV/metrics. Human judgments are excluded from judge prompts; judge failures remain separate. Calibration is the default split. See [workflow and commands](evals/log_judge_workflow.md). No measured alignment is claimed without actual human labels and live predictions.

## End-to-end quality pipeline (Section 35)

`uv run python evals/run_evals.py --run-live` runs the CSV agent batch, applies the existing log judge and saves good/bad counts, quality percentages, trajectory diagnostics and separate agent/judge costs and wall time. Errors remain separate; reports and manifests support controlled comparisons with --compare. See [pipeline instructions](evals/end_to_end_workflow.md). No human alignment or live quality score is claimed until measured.

## Synthetic evaluation data (Section 36)

The main notebook adds course-style persona questions/reference answers from numbered CTI report text, bulk CSV/JSON generation, exact line provenance and source hashes, followed by the existing agent and reference-aware judge. Generated references remain unreviewed candidates, not human gold. Source checks run before evaluation; references are withheld from the agent. See [workflow](evals/synthetic_workflow.md). Paid generation/evaluation switches default false.

Section 37 adds the course's standalone agent-only synthetic CSV runner: `evals/run_evals_synthetic.py`, with --questions/--output/--limit/--concurrency, default concurrency 5, fresh per-question agents and shared cached tools. It preserves full reference rows for later judging and saves dated _synthetic.json plus cost/token/error/time summaries. Add --run-live to authorize paid collection.

## Three-dimensional synthetic judging (Section 38)

`evals/judge_checks.py` defines independent correctness, instruction-following and trajectory judges. `evals/run_judge_checks.py` runs bounded parallel checks with checkpointed _judged.json, per-check usage/costs and summaries. `evals/explore_judge_results.py` provides a filterable Streamlit browser on port 8503. Missing evidence and provider errors stay distinct from bad verdicts; historical instructions are captured in new collection outputs. See [instructions](evals/three_judges_workflow.md).
