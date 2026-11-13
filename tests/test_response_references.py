"""New references remain typed and streamable without breaking old course records."""
import json
import pytest
from pydantic import ValidationError
from models import RAGResponse, Reference
from course_structured_agent import RAGResponse as EarlierRAGResponse
from structured_stream import StructuredStreamDisplay
from tests.test_pydantic_ai_course import PAYLOAD


@pytest.mark.parametrize('field', ['file_path','explanation'])
def test_reference_rejects_empty_fields(field):
    with pytest.raises(ValidationError):
        Reference.model_validate({'file_path':'AA24-038A.txt','explanation':'Supports the answer.',field:'   '})


def test_earlier_records_remain_readable_and_original_schema_unchanged():
    earlier=EarlierRAGResponse.model_validate(PAYLOAD)
    application=RAGResponse.model_validate(PAYLOAD)
    assert application.answer==earlier.answer
    assert application.references==[]
    assert 'references' not in EarlierRAGResponse.model_fields


@pytest.mark.asyncio
async def test_references_emit_when_array_items_complete():
    fields=[]
    display=StructuredStreamDisplay(lambda name,value:fields.append((name,value)))
    reference={'file_path':'AA24-038A.txt','explanation':'Supports credential-access reporting.'}
    raw=json.dumps({**PAYLOAD,'references':[reference]})
    split=raw.index('Supports')+5
    await display({'kind':'partial-json','call_index':0,'json':raw[:split]})
    assert not [v for n,v in fields if n=='reference']
    await display({'kind':'partial-json','call_index':0,'json':raw})
    assert [v for n,v in fields if n=='reference']==[reference]
    assert ''.join(v for n,v in fields if n=='answer_chunk')==PAYLOAD['answer']
