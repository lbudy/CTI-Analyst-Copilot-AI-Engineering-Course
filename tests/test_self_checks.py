"""Check schema and plain-text judge input without treating self-checks as proof."""
import pytest
from pydantic import ValidationError
from models import Check,RAGResponse
from tests.test_pydantic_ai_course import PAYLOAD


def test_text_rendering_preserves_code_references_and_failed_checks():
    code='Proposed analyst code\n```python\nx = 1\n```'
    response=RAGResponse.model_validate({**PAYLOAD,'answer':code,
        'references':[{'file_path':'AA24-038A.txt','explanation':'Source context.'}],
        'checks':[{'rule':'Formatting','passed':False,'explanation':'Needs correction.'}]})
    rendered=response.to_string()
    assert str(response)==rendered
    assert code in rendered
    assert 'reference: AA24-038A.txt — Source context.' in rendered
    assert 'self_check: [-] Formatting — Needs correction.' in rendered
    assert 'found_answer: True' in rendered
    assert not rendered.startswith('{')


def test_legacy_response_is_readable_without_invented_checks():
    output=RAGResponse.model_validate(PAYLOAD)
    assert output.checks==[]
    assert output.references==[]


@pytest.mark.parametrize('values',[
    {'rule':'','passed':True,'explanation':'Evidence'},
    {'rule':'Rule','passed':'true','explanation':'Evidence'},
    {'rule':'Rule','passed':True,'explanation':''},
])
def test_check_requires_strict_boolean_and_nonempty_evidence(values):
    with pytest.raises(ValidationError):
        Check.model_validate(values)
