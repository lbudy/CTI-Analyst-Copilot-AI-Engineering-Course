"""Exercise chat, streaming events, follow-ups and persistence without provider calls."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest

pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
from models import RAGResponse


def test_chat_followups_activity_cache_and_clear():
    requests = []
    answer = RAGResponse(answer='A source-grounded test answer.', found_answer=True, confidence=.75,
                         confidence_explanation='Fixture', answer_type='explanation',
                         followup_questions=['Show the supporting evidence', 'What is unknown?'],
                         references=[{'file_path':'AA24-109A.txt','explanation':'Supports the reported Akira behavior.'}])
    async def fake_run(agent, prompt, history, on_event):
        requests.append((prompt, list(history)))
        await on_event({'kind':'tool-call', 'tool':'search', 'args':{'query':prompt}})
        await on_event({'kind':'tool-call', 'tool':'get_file', 'args':{'filename':'AA24-109A.txt'}})
        raw = json.dumps(answer.model_dump())
        await on_event({'kind':'partial-json','call_index':0,'json':raw[:30]})
        await on_event({'kind':'partial-json','call_index':0,'json':raw})
        return SimpleNamespace(output=answer, new_messages=lambda: ['user', 'assistant'])
    with patch('doc_agent.create_agent', return_value=object()) as create, \
         patch('doc_agent.run_agent_stream', side_effect=fake_run):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=20).run()
        assert not app.exception
        app.chat_input[0].set_value('What does Akira target?').run()
        assert not app.exception
        assert len(app.chat_message)==2
        assert any(status.label=='Done' for status in app.status)
        assert any('Read report:' in m.value and 'ic3.gov' in m.value for m in app.markdown)
        assert any('75%' in c.value for c in app.caption)
        assert any('[AA24-109A.txt]' in m.value and 'ic3.gov' in m.value for m in app.markdown)
        assert any('Supports the reported Akira behavior.' in c.value for c in app.caption)
        assert any('Found in reports: Yes' in c.value for c in app.caption)
        app.button(key='followup-2-0').click().run()
        assert not app.exception
        assert requests[1][0]=='Show the supporting evidence'
        assert requests[1][1]==['user','assistant']
        assert len(app.chat_message)==4
        assert len(app.status)==2
        assert sum('Supports the reported Akira behavior.' in c.value for c in app.caption)==2
        assert create.call_count==1
        app.run()
        assert len(requests)==2
        assert len(app.status)==2
        app.sidebar.button[0].click().run()
        assert not app.exception
        assert len(app.chat_message)==0
        assert not app.session_state['history']
        assert create.call_count==1
        app.session_state['cti_runtime']['loop'].close()


def test_failed_stream_preserves_activity_and_hides_unvalidated_answer():
    async def failing(agent, prompt, history, on_event):
        await on_event({'kind':'tool-call','tool':'search','args':{'query':prompt}})
        await on_event({'kind':'partial-json','call_index':0,'json':'{"answer":"Unvalidated partial'})
        raise RuntimeError('fixture error')
    with patch('doc_agent.create_agent', return_value=object()), \
         patch('doc_agent.run_agent_stream', side_effect=failing):
        app=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=20).run()
        app.chat_input[0].set_value('A failing question').run()
        assert not app.exception
        assert app.error
        assert app.status[0].label=='Incomplete'
        assert not any('Unvalidated partial' in m.value for m in app.markdown)
        assert len(app.session_state['history'])==0
        assert len(app.button)==1  # sidebar clear only, no stale follow-ups
        app.run()
        assert app.error
        app.session_state['cti_runtime']['loop'].close()


@pytest.mark.parametrize('value,expected', [(1, 1), (0, -1)])
def test_feedback_numeric_mapping_and_followup_text(value, expected):
    import app
    state = SimpleNamespace(monitoring_session={'id': 's', 'context': {}}, pending_question=None)
    state.get = lambda key: value
    with patch.object(app.st, 'session_state', state), patch.object(app, 'interaction') as event, patch.object(app.st, 'toast') as toast:
        app.record_feedback('answer-123', 'feedback-answer-123')
        event.assert_called_once_with(state.monitoring_session, 'user_feedback', turn_id='answer-123', feedback=expected)
        toast.assert_called_once()
        event.reset_mock()
        app.choose_followup('Which report supports this?')
        event.assert_called_once_with(state.monitoring_session, 'followup_question_clicked', question='Which report supports this?')
        assert state.pending_question == 'Which report supports this?'
