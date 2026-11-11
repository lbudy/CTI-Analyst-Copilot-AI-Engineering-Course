"""Optional frontend: uv run --extra ui streamlit run app.py."""
import asyncio
import streamlit as st
from dotenv import load_dotenv
from doc_agent import DocumentationAgentConfig, create_agent, run_agent_stream
from tools import ROOT, create_documentation_tools_cached
from structured_stream import StructuredStreamDisplay

st.set_page_config(page_title='CTI Analyst Copilot', layout='wide')
st.title('CTI Analyst Copilot — report research')
st.caption('Evidence-grounded research. Analyst review is required before operational use.')
load_dotenv(ROOT / '.env')
if 'history' not in st.session_state:
    st.session_state.history = []
    st.session_state.turns = []
if st.sidebar.button('Clear conversation'):
    st.session_state.history = []
    st.session_state.turns = []
    st.rerun()
for turn in st.session_state.turns:
    with st.chat_message(turn['role']):
        st.markdown(turn['content'])
question = st.chat_input('Ask about the local threat reports')
if question:
    with st.chat_message('user'):
        st.markdown(question)
    with st.chat_message('assistant'):
        preview = st.empty()
        activity = st.status('Research in progress')
        chunks = []
        def show_field(name, value):
            if name == 'answer_chunk':
                chunks.append(value)
                preview.markdown('**Provisional answer**\n\n' + ''.join(chunks))
            elif name == 'tool-call':
                activity.write({'tool': value['tool'], 'arguments': value['args']})
            else:
                activity.write({name: value})
        async def run():
            # Per-run agent avoids sharing asynchronous state between sessions.
            agent = create_agent(DocumentationAgentConfig(), create_documentation_tools_cached())
            return await run_agent_stream(agent, question, st.session_state.history,
                                          on_event=StructuredStreamDisplay(show_field))
        try:
            result = asyncio.run(run())
        except Exception as exc:
            preview.empty()
            activity.update(label='Research incomplete', state='error')
            st.error(f'No validated answer was produced: {type(exc).__name__}')
        else:
            preview.markdown(result.output.answer)
            st.json(result.output.model_dump())
            st.write('Token usage', result.usage)
            activity.update(label='Research complete — review evidence', state='complete')
            st.session_state.history.extend(result.new_messages())
            st.session_state.turns.extend([{'role': 'user', 'content': question},
                                          {'role': 'assistant', 'content': result.output.answer}])
