"""Run: uv run --extra ui streamlit run evals/label_evals.py."""
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

import streamlit as st
import streamlit.components.v1 as components
from evals.labeling import load_records,get_results_path,save_records,find_next_unlabelled,export_gold_labels
from evals.quality import RUBRIC
from tools import load_reports


def main():
    st.set_page_config(layout='wide',page_title='CTI evaluation labeling')
    st.markdown('<div id="label-top"></div>', unsafe_allow_html=True)
    if st.session_state.pop('label_scroll_top', False):
        components.html('''<script>setTimeout(() => {
            const anchor = window.parent.document.getElementById('label-top');
            if (anchor) anchor.scrollIntoView({behavior: 'instant', block: 'start'});
        }, 100);</script>''', height=0)
    st.title('CTI evaluation labeling')
    directory=Path(st.sidebar.text_input('Evaluation directory',value=os.getenv('CTI_EVALS_DIR',str(ROOT/'outputs'))))
    files=sorted(p for p in directory.rglob('*.json') if not p.name.endswith(('_results.json','.summary.json')))
    if not files:
        st.info('No JSON files found. Run the CSV batch first or select a directory containing saved results.')
        return
    selected=st.sidebar.selectbox('Select evaluation file',files,format_func=lambda p:str(p.relative_to(directory)))
    try:
        # Validate persisted state before showing it; never silently reuse stale labels.
        loaded=load_records(selected)
    except (ValueError,KeyError,TypeError) as exc:
        st.error(str(exc))
        return
    if st.session_state.get('label_file')!=str(selected):
        st.session_state.label_file=str(selected)
        st.session_state.label_data=loaded
        st.session_state.label_index=next((i for i,r in enumerate(loaded) if r.get('label') is None),0)
    records=st.session_state.label_data
    count=sum(r.get('label') is not None for r in records)
    st.sidebar.progress(count/len(records))
    st.sidebar.caption(f'Labeled: {count} / {len(records)}')
    index=st.sidebar.selectbox('Select run',range(len(records)),
        index=st.session_state.label_index,
        format_func=lambda i:f"{i+1}. [{records[i].get('label') or 'unlabeled'}] {records[i]['input']['question'][:60]}",
        key=f'nav-{selected}-{st.session_state.label_index}')
    if index!=st.session_state.label_index:
        st.session_state.label_index=index
        st.session_state.label_scroll_top=True
        st.rerun()
    item=records[index]
    if count==len(records):
        st.success('All runs have been labeled. You can still review or revise them.')
    st.header(f'Run {index+1} / {len(records)}')
    st.subheader('User question')
    st.markdown(item['input']['question'])
    st.subheader('Agent answer')
    rag=item.get('rag_response') or {}
    if item.get('status')=='error':
        st.error(item.get('error','No validated response; execution failure.'))
    st.markdown(rag.get('answer','No validated answer available.'))
    sources={f"{r['report_id']}.txt":r['source_url'] for r in load_reports()}
    for ref in rag.get('references',[]):
        path=ref.get('file_path','')
        url=sources.get(path)
        if url:
            st.link_button(path,url)
        else:
            st.write(path+' — source URL unavailable')
        st.caption(ref.get('explanation',''))
    columns=st.columns(3)
    columns[0].caption(f"Confidence: {rag.get('confidence','unknown')}")
    columns[0].caption(rag.get('confidence_explanation',''))
    columns[1].caption(f"Answer type: {rag.get('answer_type','unknown')}")
    columns[2].caption(f"Found evidence: {rag.get('found_answer','unknown')}")
    with st.expander('Self-checks (model claims, not independent verification)'):
        st.json(rag.get('checks',[]))
    with st.expander('Tool calls'):
        st.json(item.get('tools',[]))
    with st.expander('Retrieved context and full messages'):
        st.json(item.get('messages',[]))
    with st.expander('System instructions'):
        # Never present the current prompt as the historical one.
        instructions=[part.get('content') for message in item.get('messages',[]) for part in message.get('parts',[])
                      if part.get('part_kind')=='system-prompt']
        st.write(item.get('system_instructions') or '\n'.join(str(v) for v in instructions) or
                 'Historical system instructions were not captured in this record.')
    with st.expander('Correctness rubric'):
        st.write(RUBRIC)
    st.divider()
    st.subheader('Labeling decision')
    identity=f'{selected}-{index}'
    reviewer=st.text_input('Reviewer',value=item.get('reviewer',''),key=f'reviewer-{identity}')
    current=item.get('label')
    options=['Not selected','Good','Not Good']
    decision=st.radio('Did the agent do its job correctly?',options,
        index=1 if current=='good' else 2 if current=='bad' else 0,key=f'decision-{identity}')
    comments=st.text_area('Comments / rationale',value=item.get('comments',''),key=f'comments-{identity}')
    tags=st.text_input('Failure tags (optional, comma-separated)',value=', '.join(item.get('failure_tags',[])),key=f'tags-{identity}')
    if st.button('Save Label & Next',type='primary'):
        if decision=='Not selected' or not reviewer.strip() or not comments.strip():
            st.error('Choose a decision and enter a reviewer and rationale before saving.')
        else:
            item.update(label='good' if decision=='Good' else 'bad',comments=comments.strip(),
                        reviewer=reviewer.strip(),failure_tags=[t.strip() for t in tags.split(',') if t.strip()])
            save_records(records,get_results_path(selected))
            next_index=find_next_unlabelled(records,index)
            if next_index is not None:
                st.session_state.label_index=next_index
            st.session_state.label_scroll_top=True
            st.rerun()
    st.sidebar.caption(f'Saves to {get_results_path(selected).name}')
    try:
        gold=export_gold_labels(records)
    except (ValueError,KeyError,TypeError):
        st.sidebar.caption('Gold-label export requires matching CTI case metadata. Review annotations are still saved.')
    else:
        st.sidebar.download_button('Download Section 30 human labels',json.dumps(gold,indent=2),
                                   file_name='human_labels.json',mime='application/json')


if __name__=='__main__':
    main()
