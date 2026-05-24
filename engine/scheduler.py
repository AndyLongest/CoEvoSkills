from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")


class Scheduler:
    """Parallel worker scheduler for task-level parallelism.

    Supports parallel evolution (4 workers) and evaluation (10 workers)
    as specified in the paper (§4.1, Table A1).

    Uses ThreadPoolExecutor for simplicity. For CPU-bound or Docker-heavy
    workloads, ProcessPoolExecutor may be more appropriate.
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None

    def map(self, fn: Callable[..., T], items: list, *args, **kwargs) -> list[T]:
        """Execute fn(item) for each item in parallel.

        Results are returned in the same order as items.

        Args:
            fn: Function to execute for each item.
            items: List of items to process.
            *args, **kwargs: Additional arguments passed to fn.

        Returns:
            List of results in the same order as items.
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(fn, item, *args, **kwargs): i
                for i, item in enumerate(items)
            }
            results: list = [None] * len(items)
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = e
        return results

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit a single task for async execution."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._executor.submit(fn, *args, **kwargs)

    def shutdown(self) -> None:
        """Clean up the thread pool."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()
