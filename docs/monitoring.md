# Logfire monitoring — Section 26

1. Create a project at https://logfire.pydantic.dev or https://logfire-eu.pydantic.dev and create a write token.
2. Set `LOGFIRE_TOKEN` in the existing gitignored `.env`. Use the regional `LOGFIRE_BASE_URL` given by your project setup. No secret is needed in GitHub code or the notebook.
3. Set `LOGFIRE_INCLUDE_CONTENT=true` to upload full model prompts/responses and tool content. Default false still allows timing, tool/model identities and usage metadata. Changing this option requires restarting Streamlit because instrumentation initializes once per process.
4. Run `uv run --extra ui streamlit run app.py`. Open port 8501 in Codespaces.
5. Ask a question, click a suggested follow-up and use the thumbs feedback control. Inspect Live traces in your own Logfire project.

The SDK is a main dependency. `monitoring.py` configures Logfire once and instruments Pydantic AI before app agent creation. No token means no Logfire export. Other explicitly configured OpenTelemetry exporters may still operate. Do not instrument the underlying OpenAI client a second time: Pydantic AI already provides the model spans.

Each Streamlit conversation creates a `streamlit_session` span and saves `logfire.get_context()` in session state. The root finishes immediately, as in the course. `logfire.attach_context()` restores its context around subsequent turns and feedback, so they remain children in the same trace even after the root finishes. Clearing conversation immediately captures a fresh parent context. Context is detached on exit, preventing leakage between unrelated users. The root duration is not the conversation duration; child spans retain their own timing. Every child interaction carries a random session_id; successful answers receive turn IDs for correlating feedback. User-submitted text is captured by Pydantic AI only when content capture is enabled; UI events record identifiers, not extra copies of questions.

Check one real question for nested agent/model/tool spans, provider usage and latency. Check a second question shares its session parent. Check clear creates a new parent. A follow-up emits `followup_question_clicked` with the actual `question` text; thumbs emit `user_feedback` with `turn_id` and numeric `feedback` (+1 or -1). Failures should appear on the interaction span. Costs in the dashboard rely on supported pricing and are estimates; existing test JSONL costs remain independent.

## Downloading and reconstructing traces

Create a project read token (separate from the write token) and put it in `LOGFIRE_READ_TOKEN`. Run:

```bash
uv run python scripts/download_logfire_traces.py
```

This downloads up to 10,000 records from the last 24 hours into the gitignored `outputs/logfire_traces.json`. Increase the limit or use narrower time windows for larger projects. SQL selects only this application's service_name. Group records by trace_id; build the tree using span_id and parent_span_id; order by start_timestamp. Inspect attributes for tool, usage, feedback and model-message content. Full content reconstruction depends on the content option, retained records and scrubbing. Trace reconstruction does not automatically recreate Pydantic AI message objects or replay tool effects.

No dashboard upload or SQL download is claimed verified until configured with your project's credentials. No account or project is created by the application.

Official references: [Pydantic AI integration](https://pydantic.dev/docs/ai/integrations/logfire/), [write tokens](https://pydantic.dev/docs/logfire/manage/create-write-tokens/), [query API](https://pydantic.dev/docs/logfire/manage/query-api/).

The course context-propagation pattern is shown step by step in notebook Section 27. [Official propagation API](https://pydantic.dev/docs/logfire/api/propagate/).

## User interaction events — Section 28

The existing thumbs control maps Streamlit's 1 (up) to +1 and 0 (down) to -1; clearing a selection (None) sends no vote. Selection changes emit a new event; they are events, not a deduplicated current-rating table. Each vote includes turn_id for answer correlation, while both event types inherit the saved conversation trace. The callback runs only on interaction, so normal reruns do not resend feedback. A toast acknowledges the selection.

Follow-up question text is deliberately captured as the `question` event attribute, independently of LOGFIRE_INCLUDE_CONTENT. That flag controls Pydantic AI content capture, not explicitly logged UI attributes. Logfire's scrubbing can redact sensitive values. Event message names are stable for SQL filtering:

```sql
SELECT start_timestamp, trace_id, attributes
FROM records
WHERE service_name = 'cti-analyst-copilot'
  AND message IN ('followup_question_clicked', 'user_feedback')
ORDER BY start_timestamp
```

Restart the app, ask a question, click a follow-up, then click thumbs up/down. Inspect those exact messages and attributes in the same trace. No regenerate/reference-click/clipboard tracking was added by this lesson.
