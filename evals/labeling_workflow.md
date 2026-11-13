# Human labeling app — Section 33

Adapted from the course app supplied by the user, in `evals/label_evals.py`. Launch within this repository:

```bash
uv run --extra ui streamlit run evals/label_evals.py --server.port 8502
```

Open port 8502 in Codespaces. This interface labels data already collected; it makes no model calls. The existing research chat and approval gates remain intact.

Select a directory (default outputs), then the dated CSV batch JSON. Inspect question, answer, clickable original report sources, confidence/type, model self-checks, tool calls and retrieved context. The current system prompt is not misrepresented as a historical prompt: captured instructions are shown if available; otherwise a gap is stated. When collection omitted full evidence, verify original sources manually before labeling.

At the bottom choose Good or Not Good, enter reviewer and rationale, and optional failure tags. Save Label & Next writes `<input_stem>_results.json`, retaining all run data plus annotations, then moves to the next unlabeled run. It wraps, resumes saved progress after restart and allows revising prior decisions. No default decision is selected. Atomic replacement protects the previous file from a partial write. Source hashes reject reuse of saved labels after the original responses change. Use one reviewer per results file to avoid concurrent edits overwriting each other.

Supported inputs: course-shaped batch lists, lists of Section 30 run records, and the reconstructed Logfire archive mapping trace IDs to TraceData records. Unsupported JSON types show an explanation. The app does not query Logfire itself. For grouped archive histories it displays the final question/output and all reconstructed messages; labeling that final response is not independent labeling of every prior turn. Missing/unsupported telemetry cannot be restored by the UI.

For the default CTI catalog the sidebar exports reviewed completed responses in the existing HumanLabel schema. Download human_labels.json and place it in the matching quality batch directory produced by Section 31's conversion cell. Matching hashes are required; no human verdicts are automatically assigned. Arbitrary Logfire questions need corresponding reviewed case metadata first. Execution errors retain annotations but are excluded from completed-response gold labels. Partial exports do not bypass the evaluator's complete-split checks.

Correctness: supported answers or justified scoped refusals pass; hallucinations, wrong scope, incorrect facts/citations or missing available evidence fail. Labels require actual analyst review. Model confidence, self-checks, feedback and the original course author's observations do not establish correctness in this project. Do not fabricate labels or force a good/bad balance.

Tests: `uv run pytest tests/test_label_evals.py -q` covers persistence, unchanged originals, source mismatch, navigation and Streamlit save/resume behavior.
