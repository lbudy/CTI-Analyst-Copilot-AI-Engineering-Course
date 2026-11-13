"""Run: uv run --extra ui streamlit run evals/explore_judge_results.py --server.port 8503."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import streamlit as st
from evals.judge_checks import CHECK_KEYS,captured_instructions,reference_data
from evals.run_judge_checks import check_summary


def score_state(entry,key):
    verdict=entry.get(key,{})
    if verdict.get('status')=='error':return 'error'
    if verdict.get('score') in {'good','bad'}:return verdict['score']
    return 'missing'


def filter_entries(entries,filters):
    return [(i,entry) for i,entry in enumerate(entries)
            if all(value=='all' or score_state(entry,key)==value for key,value in filters.items())]


def main():
    st.set_page_config(layout='wide',page_title='CTI judge results explorer')
    st.title('Three-judge results explorer')
    directory=Path(st.sidebar.text_input('Results directory',os.getenv('CTI_JUDGED_DIR',str(ROOT/'outputs'))))
    files=sorted(directory.rglob('*_judged.json'))
    if not files:
        st.info('No *_judged.json files found. Run evals/run_judge_checks.py first.')
        return
    selected=st.sidebar.selectbox('Select judged file',files,format_func=lambda p:str(p.relative_to(directory)))
    try:
        entries=json.loads(selected.read_text())
        if not isinstance(entries,list) or not entries or any(not isinstance(e,dict) or 'input' not in e for e in entries):
            raise ValueError('Expected a nonempty list of judged entries')
    except (ValueError,OSError) as exc:
        st.error(str(exc));return
    filters={key:st.sidebar.selectbox(name,['all','good','bad','error','missing'],key=key) for name,key in CHECK_KEYS}
    summary=check_summary(entries)
    for name,key in CHECK_KEYS:
        row=summary[key]
        st.sidebar.caption(f"{name}: {row['good']}/{len(entries)} good; {row['bad']} bad; {row['unclassified']} unclassified")
    filtered=filter_entries(entries,filters)
    st.sidebar.caption(f'Showing {len(filtered)} / {len(entries)} entries')
    if not filtered:
        st.warning('No entries match the selected filters.');return
    original_index,entry=st.sidebar.selectbox('Select entry',filtered,
        format_func=lambda pair:f"#{pair[0]+1}: {pair[1]['input'].get('question','')[:70]}")
    st.header(f'Entry {original_index+1} / {len(entries)}')
    for col,(name,key) in zip(st.columns(3),CHECK_KEYS):col.metric(name,score_state(entry,key))
    ref=reference_data(entry);rag=entry.get('rag_response') or {}
    st.subheader('Question');st.markdown(entry['input'].get('question',''))
    st.subheader('Generated reference answer');st.info(ref.get('reference_answer','Unavailable'))
    st.caption(f"Source: {ref.get('filename','unknown')}; lines {ref.get('line_number_start','?')}–{ref.get('line_number_end','?')}")
    with st.expander('Reference supporting passage'):st.write(ref.get('supporting_passage','Not captured'))
    st.subheader('Agent answer');st.markdown(rag.get('answer','No completed answer'))
    cost=entry.get('cost')
    st.caption(f'Agent estimated cost: ${cost:.6f}' if isinstance(cost,(float,int)) else 'Agent cost unavailable')
    st.caption(f"Confidence: {rag.get('confidence','unknown')}; type: {rag.get('answer_type','unknown')}; found: {rag.get('found_answer','unknown')}")
    from tools import load_reports
    sources={f"{r['report_id']}.txt":r['source_url'] for r in load_reports()}
    for reference in rag.get('references',[]):
        path=reference.get('file_path','')
        if path in sources:st.link_button(path,sources[path])
        else:st.write(path)
        st.caption(reference.get('explanation',''))
    with st.expander('Self-checks and follow-ups'):
        st.json({'checks':rag.get('checks',[]),'followup_questions':rag.get('followup_questions',[])})
    with st.expander('Tool trajectory'):st.json(entry.get('tools',[]))
    with st.expander('Messages and retrieved evidence'):st.json(entry.get('messages',[]))
    st.subheader('Judge evaluations')
    for tab,(name,key) in zip(st.tabs([name for name,_ in CHECK_KEYS]),CHECK_KEYS):
        with tab:
            verdict=entry.get(key,{})
            st.write('Score: '+score_state(entry,key))
            st.markdown(verdict.get('reasoning','Not evaluated'))
            if verdict.get('suggestion') and verdict['suggestion']!='none':st.info(verdict['suggestion'])
            with st.expander('Judge usage and cost'):st.json(verdict)
    with st.expander('Historical agent instructions'):
        st.write(captured_instructions(entry) or 'Not captured; current instructions are not substituted.')


if __name__=='__main__':main()
