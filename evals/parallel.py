"""Course tqdm mapping snippets with bounded work and explicit ordering."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tqdm.auto import tqdm


async def async_map_progress(seq, func, max_concurrency=6, *, progress=True, on_result=None):
    """Async semaphore mapping; results arrive in completion order, as in the course."""
    if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or max_concurrency < 1:
        raise ValueError('max_concurrency must be a positive integer')
    seq = list(seq)
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_with_semaphore(item):
        async with semaphore:
            return await func(item)

    tasks = [asyncio.create_task(run_with_semaphore(item)) for item in seq]
    results = []
    try:
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), disable=not progress):
            result = await future
            if on_result is not None:
                on_result(result)
            results.append(result)
        return results
    finally:
        # Do not leave paid requests running in the background on cancellation/error.
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def threaded_map_progress(pool, seq, func, *, progress=True):
    """Use a caller-owned executor; return results in submission order."""
    seq = list(seq)
    futures = []
    with tqdm(total=len(seq), disable=not progress) as bar:
        try:
            for item in seq:
                future = pool.submit(func, item)
                future.add_done_callback(lambda _: bar.update())
                futures.append(future)
            return [future.result() for future in futures]
        finally:
            for future in futures:
                future.cancel()
            # Wait for running callbacks before closing the progress bar. Keep the
            # supplied pool open for reuse; running Python threads cannot be killed.
            from concurrent.futures import wait
            wait(futures)
