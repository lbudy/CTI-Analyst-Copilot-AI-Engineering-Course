"""Monitoring configuration and session context without remote export."""
from unittest.mock import patch
import monitoring


def test_configure_once_and_explicit_content(monkeypatch):
    monkeypatch.setattr(monitoring, '_configured', False)
    monkeypatch.setenv('LOGFIRE_INCLUDE_CONTENT', 'true')
    with patch.object(monitoring.logfire, 'configure') as configure, patch.object(monitoring.logfire, 'instrument_pydantic_ai') as instrument:
        monitoring.configure_monitoring()
        monitoring.configure_monitoring()
    assert configure.call_count == 1
    assert configure.call_args.kwargs['send_to_logfire'] == 'if-token-present'
    instrument.assert_called_once_with(include_content=True)
    monkeypatch.setattr(monitoring, '_configured', False)


def test_interactions_share_session_parent_and_feedback():
    from opentelemetry import trace
    session = monitoring.new_session()
    with monitoring.session_scope(session):
        assert trace.get_current_span() is not None
    with patch.object(monitoring.logfire, 'info') as info:
        monitoring.interaction(session, 'user_feedback', turn_id='turn-1', feedback=1)
    assert info.call_args.kwargs['session_id'] == session['id']
    assert info.call_args.args == ('user_feedback',)
    assert info.call_args.kwargs['feedback'] == 1


def test_saved_context_groups_turns_and_reset_starts_new_trace():
    # Isolate global SDK configuration from the app/tests; never export remotely.
    import subprocess
    import sys
    code = '''
import logfire
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from monitoring import new_session, session_scope, interaction
exporter = InMemorySpanExporter()
logfire.configure(send_to_logfire=False, console=False, metrics=False,
    additional_span_processors=[SimpleSpanProcessor(exporter)])
session = new_session()
for label in ['first_question', 'followup_question']:
    with session_scope(session):
        with logfire.span(label):
            pass
interaction(session, 'followup_question_clicked', question='What evidence supports this?')
interaction(session, 'user_feedback', feedback=-1, turn_id='turn-1')
fresh = new_session()
with session_scope(fresh):
    with logfire.span('after_clear'):
        pass
logfire.force_flush()
spans = exporter.get_finished_spans()
by_name = {span.name: span for span in spans if span.name != 'streamlit_session'}
first = by_name['first_question'].context.trace_id
assert first == by_name['followup_question'].context.trace_id
assert first != by_name['after_clear'].context.trace_id
roots = {span.context.span_id: span for span in spans if span.name == 'streamlit_session'}
turns = [span for span in spans if span.name == 'CTI user interaction']
assert len(turns) == 5
assert all(span.parent.span_id in roots for span in turns)
assert len({span.context.trace_id for span in roots.values()}) == 2
events = {span.name: span for span in spans if span.name in {'followup_question_clicked', 'user_feedback'}}
assert events['followup_question_clicked'].attributes['question'] == 'What evidence supports this?'
assert events['user_feedback'].attributes['feedback'] == -1
assert all(span.context.trace_id == first for span in events.values())
'''
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)
