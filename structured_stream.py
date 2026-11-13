"""Optional jaxn parsing: provisional fields are never treated as validated output."""
from jaxn import JSONParserHandler, StreamingJSONParser


class RAGResponseHandler(JSONParserHandler):
    def __init__(self, on_field):
        self.on_field = on_field

    def on_value_chunk(self, path, field_name, chunk):
        if path == '' and field_name == 'answer':
            self.on_field('answer_chunk', chunk)

    def on_field_end(self, path, field_name, value, parsed_value=None):
        if path == '' and field_name in {'confidence', 'answer_type'}:
            self.on_field(field_name, parsed_value if parsed_value is not None else value)

    def on_array_item_end(self, path, field_name, item=None):
        if field_name == 'followup_questions':
            self.on_field('followup_question', item)
        elif field_name == 'references' and isinstance(item, dict):
            self.on_field('reference', item)


class StructuredStreamDisplay:
    def __init__(self, on_field):
        self.on_field = on_field
        self.calls = {}

    async def __call__(self, event):
        if event['kind'] == 'tool-call':
            self.on_field('tool-call', event)
            return
        if event['kind'] != 'partial-json':
            return
        key = event['call_index']
        previous, parser = self.calls.get(key, ('', None))
        current = event['json']
        if parser is None or not current.startswith(previous):
            parser = StreamingJSONParser(RAGResponseHandler(self.on_field))
            previous = ''
        parser.parse_incremental(current[len(previous):])
        self.calls[key] = (current, parser)
