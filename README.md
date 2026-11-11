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
