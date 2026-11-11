"""Run: uv run python main.py --question 'What does Akira target?' [--stream]."""
import argparse
import asyncio
from dotenv import load_dotenv
from pydantic_ai.usage import RunUsage
from doc_agent import DocumentationAgentConfig, create_agent, run_agent, run_agent_stream, run_agent_stream_text, run_agent_stream_simple
from pydantic_search_tools import print_messages
from tools import ROOT, create_documentation_tools_cached


async def run_qna(agent):
    messages, usage = [], RunUsage()
    while True:
        prompt = input('You: ').strip()
        if prompt.lower() == 'stop':
            break
        if not prompt:
            continue
        result = await run_agent(agent, prompt, messages)
        messages.extend(result.new_messages())
        usage += result.usage
        print(result.output.model_dump_json(indent=2))
    print(usage)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--question')
    parser.add_argument('--stream', action='store_true', help='Existing structured graph stream')
    parser.add_argument('--stream-mode', choices=['simple', 'text', 'structured'])
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    mode = args.stream_mode or ('structured' if args.stream else None)
    if mode and not args.question:
        parser.error('--stream or --stream-mode requires --question')
    agent = create_agent(DocumentationAgentConfig(), create_documentation_tools_cached(),
                         **({'output_type': str} if mode in {'simple', 'text'} else {}))
    if args.question:
        runner = {'simple': run_agent_stream_simple, 'text': run_agent_stream_text,
                  'structured': run_agent_stream}.get(mode, run_agent)
        result = await runner(agent, args.question)
        print_messages(result.new_messages())
        output = await result.get_output() if mode == 'simple' else result.output
        print(output if isinstance(output, str) else output.model_dump_json(indent=2))
        print(result.usage)
    else:
        await run_qna(agent)


if __name__ == '__main__':
    asyncio.run(main())
