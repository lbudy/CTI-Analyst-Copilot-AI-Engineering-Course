"""CTI chat UI. Run: uv run --extra ui streamlit run app.py.

Keep this filename: streamlit.py would shadow the installed Streamlit package.
Agent, tools, and their research/approval behavior are unchanged.
"""
import asyncio
import hashlib
import json
from uuid import uuid4
from urllib.parse import urlsplit

import streamlit as st
from dotenv import load_dotenv
from jaxn import StreamingJSONParser

from doc_agent import DocumentationAgentConfig, create_agent, run_agent_stream, DEFAULT_INSTRUCTIONS
from structured_stream import RAGResponseHandler
from tools import ROOT, create_documentation_tools_cached, load_reports

from monitoring import configure_monitoring, new_session, session_scope, interaction

REPOSITORY = 'https://github.com/lbudy/CTI-Analyst-Copilot-AI-Engineering-Course'


def metadata_row(metadata):
    columns = st.columns(3)
    confidence = metadata.get('confidence')
    found = metadata.get('found_answer')
    columns[0].caption(f"Type: {metadata.get('answer_type', '…')}")
    columns[1].caption(f'Confidence: {float(confidence):.0%}' if confidence is not None else 'Confidence: …')
    columns[2].caption('Found in reports: ' + ('Yes' if found is True else 'No' if found is False else '…'))


def render_references(references, sources, provisional=False):
    if not references:
        return
    st.caption('References — streaming preview' if provisional else 'References')
    for reference in references:
        path = reference.get('file_path', '')
        explanation = reference.get('explanation', '')
        source = sources.get(path)
        label = path.replace('[', r'\[').replace(']', r'\]')
        if source and urlsplit(source).scheme in {'http', 'https'}:
            st.markdown(f'[{label}](<{source}>)')
        else:
            st.write(path)
        st.caption(explanation)


def activity_line(event, sources):
    args = event.get('args', {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            args = {}
    if not isinstance(args, dict):
        args = {}
    if event['tool'] == 'search':
        return 'Search: ' + str(args.get('query', ''))
    if event['tool'] == 'get_file':
        filename = str(args.get('filename', ''))
        source = sources.get(filename)
        if source and urlsplit(source).scheme in {'http', 'https'}:
            label = filename.replace('[', r'\[').replace(']', r'\]')
            return f'Read report: [{label}](<{source}>)'
        return 'Read file: ' + filename
    return 'Tool: ' + event['tool']


class UIResponseHandler(RAGResponseHandler):
    """Capture the remaining boolean metadata without changing the agent/parser module."""
    def on_field_end(self, path, field_name, value, parsed_value=None):
        super().on_field_end(path, field_name, value, parsed_value)
        if path == '' and field_name == 'found_answer':
            found = parsed_value if isinstance(parsed_value, bool) else str(value).lower() == 'true'
            self.on_field('found_answer', found)


class UIStream:
    def __init__(self, on_field):
        self.on_field = on_field
        self.calls = {}

    async def __call__(self, event):
        if event['kind'] == 'tool-call':
            self.on_field('tool-call', event)
        elif event['kind'] == 'partial-json':
            key = event['call_index']
            previous, parser = self.calls.get(key, ('', None))
            current = event['json']
            if parser is None or not current.startswith(previous):
                parser = StreamingJSONParser(UIResponseHandler(self.on_field))
                previous = ''
                self.on_field('reset-preview', None)
            parser.parse_incremental(current[len(previous):])
            self.calls[key] = (current, parser)


def choose_followup(question):
    st.session_state.pending_question = question
    interaction(st.session_state.monitoring_session, "followup_question_clicked", question=question)


def record_feedback(turn_id, widget_key):
    value = st.session_state.get(widget_key)
    if value is not None:
        interaction(st.session_state.monitoring_session, 'user_feedback',
                    turn_id=turn_id, feedback=1 if value == 1 else -1)
        st.toast('Thanks for the feedback!', icon='👍' if value == 1 else '👎')


def render_turn(turn, sources):
    with st.chat_message(turn['role']):
        if turn['role'] == 'assistant':
            with st.status(turn.get('status', 'Done'), state=turn.get('state', 'complete'), expanded=True):
                for line in turn.get('activity', []):
                    st.markdown(line)
            if turn.get('error'):
                st.error(turn['error'])
            else:
                st.markdown(turn['content'])
                metadata_row(turn.get('metadata', {}))
                render_references(turn.get('metadata', {}).get('references', []), sources)
                if turn.get('id'):
                    key = 'feedback-' + turn['id']
                    st.feedback('thumbs', key=key, on_change=record_feedback, args=(turn['id'], key))
        else:
            st.markdown(turn['content'])


def main():
    st.set_page_config(page_title='CTI Analyst Copilot', page_icon='🔎', layout='wide')
    st.title('CTI Analyst Copilot')
    st.caption('Research across local threat reports. Analyst review remains required.')
    st.sidebar.markdown(f'[Project repository]({REPOSITORY})')
    load_dotenv(ROOT / '.env')
    configure_monitoring()
    if ('monitoring_session' not in st.session_state
            or 'context' not in st.session_state.monitoring_session):
        st.session_state.monitoring_session = new_session()
    st.session_state.setdefault('turns', [])
    st.session_state.setdefault('history', [])
    st.session_state.setdefault('pending_question', None)

    if st.sidebar.button('Clear conversation'):
        interaction(st.session_state.monitoring_session, 'clear_conversation')
        st.session_state.monitoring_session = new_session()
        st.session_state.turns = []
        st.session_state.history = []
        st.session_state.pending_question = None
        st.rerun()

    # Cache both the agent and its event loop per session. Reuse the same loop
    # across turns so async HTTP clients never refer to a loop closed by asyncio.run.
    # Rebuild a cached agent created before the references schema was introduced.
    instructions_hash = hashlib.sha256(DEFAULT_INSTRUCTIONS.encode()).hexdigest()
    previous_runtime = st.session_state.get('cti_runtime')
    if previous_runtime and (previous_runtime.get('response_schema_version') != 2
                             or previous_runtime.get('instructions_hash') != instructions_hash):
        previous_loop = previous_runtime.get('loop')
        if previous_loop is not None and not previous_loop.is_running():
            previous_loop.close()
        del st.session_state.cti_runtime
    if 'cti_runtime' not in st.session_state:
        with st.spinner('Loading index...'):
            tools = create_documentation_tools_cached()
            st.session_state.cti_runtime = {
                'agent': create_agent(DocumentationAgentConfig(), tools),
                'response_schema_version': 2,
                'instructions_hash': instructions_hash,
                'loop': asyncio.new_event_loop(),
                'sources': {f"{r['report_id']}.txt": r['source_url'] for r in load_reports()},
            }
    runtime = st.session_state.cti_runtime

    typed = st.chat_input('Ask about the threat reports')
    prompt = typed or st.session_state.pop('pending_question', None)
    if prompt and prompt.strip():
        prompt = prompt.strip()
        st.session_state.pending_question = None
        st.session_state.turns.append({'role': 'user', 'content': prompt})
    else:
        prompt = None

    for turn in st.session_state.turns:
        render_turn(turn, runtime['sources'])

    if prompt:
        turn_id = uuid4().hex
        with st.chat_message('assistant'):
            activity = st.status('Thinking...', expanded=True)
            answer_slot = st.empty()
            metadata_slot = st.empty()
            references_slot = st.empty()
            suggestions_slot = st.empty()
            chunks, activities, partial_metadata, partial_followups = [], [], {}, []
            partial_references = []

            def show_field(name, value):
                if name == 'reset-preview':
                    chunks.clear()
                    partial_metadata.clear()
                    partial_followups.clear()
                    partial_references.clear()
                    references_slot.empty()
                    answer_slot.empty()
                    metadata_slot.empty()
                    suggestions_slot.empty()
                elif name == 'answer_chunk':
                    chunks.append(value)
                    answer_slot.markdown(''.join(chunks) + ' ▌')
                elif name == 'tool-call':
                    line = activity_line(value, runtime['sources'])
                    activities.append(line)
                    activity.markdown(line)
                elif name == 'reference':
                    partial_references.append(value)
                    with references_slot.container():
                        render_references(partial_references, runtime['sources'], provisional=True)
                elif name == 'followup_question':
                    partial_followups.append(str(value))
                    suggestions_slot.caption('Suggested next questions: ' + ' · '.join(partial_followups))
                elif name in {'confidence', 'answer_type', 'found_answer'}:
                    partial_metadata[name] = value
                    with metadata_slot.container():
                        metadata_row(partial_metadata)

            try:
                with session_scope(st.session_state.monitoring_session):
                    interaction(st.session_state.monitoring_session, 'question_submitted', turn_id=turn_id)
                    result = runtime['loop'].run_until_complete(run_agent_stream(
                        runtime['agent'], prompt, st.session_state.history, on_event=UIStream(show_field)))
            except Exception as exc:
                answer_slot.empty()
                metadata_slot.empty()
                suggestions_slot.empty()
                references_slot.empty()
                activity.update(label='Incomplete', state='error', expanded=True)
                error = f'No validated answer was produced ({type(exc).__name__}). Please try again.'
                st.error(error)
                st.session_state.turns.append({'role': 'assistant', 'content': '', 'error': error,
                                               'activity': activities, 'status': 'Incomplete', 'state': 'error'})
            else:
                output = result.output.model_dump()
                answer_slot.markdown(output['answer'])
                with metadata_slot.container():
                    metadata_row(output)
                suggestions_slot.empty()
                with references_slot.container():
                    render_references(output.get('references', []), runtime['sources'])
                activity.update(label='Done', state='complete', expanded=True)
                st.session_state.history.extend(result.new_messages())
                st.session_state.turns.append({'role': 'assistant', 'id': turn_id, 'content': output['answer'],
                    'metadata': output, 'activity': activities, 'status': 'Done', 'state': 'complete'})
            st.rerun()

    # Only the latest successful assistant turn owns follow-up buttons. A new user
    # prompt suppresses the old buttons before execution, including failed runs.
    if st.session_state.turns:
        latest = st.session_state.turns[-1]
        if latest['role'] == 'assistant' and not latest.get('error'):
            questions = latest.get('metadata', {}).get('followup_questions', [])
            if questions:
                st.caption('Continue your research')
                for i, (column, question) in enumerate(zip(st.columns(len(questions)), questions)):
                    column.button(question, key=f'followup-{len(st.session_state.turns)}-{i}',
                                  on_click=choose_followup, args=(question,))


if __name__ == '__main__':
    main()
