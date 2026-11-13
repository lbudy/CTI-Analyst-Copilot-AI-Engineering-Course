"""Logfire setup and UI correlation; no credentials are stored in application code."""
import os
from contextlib import contextmanager
from threading import Lock
from uuid import uuid4

import logfire

_lock = Lock()
_configured = False


def configure_monitoring():
    """Initialize once across Streamlit reruns; content capture is explicit."""
    global _configured
    with _lock:
        if not _configured:
            logfire.configure(service_name='cti-analyst-copilot',
                              send_to_logfire='if-token-present', console=False)
            logfire.instrument_pydantic_ai(
                include_content=os.getenv('LOGFIRE_INCLUDE_CONTENT', 'false').lower() == 'true')
            _configured = True


def new_session():
    """Capture a finished session root for reuse across independent UI reruns."""
    session_id = uuid4().hex
    with logfire.span('streamlit_session', session_id=session_id):
        context = logfire.get_context()
    return {'id': session_id, 'context': context}


@contextmanager
def session_scope(session):
    with logfire.attach_context(session['context']):
        with logfire.span('CTI user interaction', session_id=session['id']):
            yield


def interaction(session, event, **attributes):
    with session_scope(session):
        logfire.info(event, event=event, session_id=session['id'], **attributes)
