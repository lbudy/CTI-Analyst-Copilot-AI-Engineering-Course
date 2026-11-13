"""Worker records remain distinct; repeated controller delivery is idempotent."""
from tests.parallel_usage import append_rows,read_rows,worker_journal,merge_rows


def test_worker_journals_are_isolated_and_merge_is_idempotent(tmp_path):
    first=worker_journal(tmp_path,'run-example','gw0')
    second=worker_journal(tmp_path,'run-example','gw1')
    a={'record_id':'one','run_id':'run-example','worker_id':'gw0','input_tokens':100}
    b={'record_id':'two','run_id':'run-example','worker_id':'gw1','input_tokens':200}
    append_rows(first,[a])
    append_rows(second,[b])
    assert read_rows(first)==[a]
    assert read_rows(second)==[b]
    combined=merge_rows(read_rows(first),read_rows(second))
    assert sum(row['input_tokens'] for row in combined)==300
    assert merge_rows(combined,[a,b])==combined


def test_distinct_calls_with_identical_counts_are_not_collapsed():
    first={'record_id':'one','model':'example','input_tokens':10}
    second={**first,'record_id':'two'}
    assert len(merge_rows([first],[second]))==2
