# src/utils/benchmark.py

import time
from typing import Callable, List, Tuple, Dict

from src.algorithms.search_algorithms import linear_search, binary_search


# -------------------------------------------------------------
#  Helper: time any search function
# -------------------------------------------------------------
def time_function(func: Callable, sequence: List[int], target: int) -> float:
    """
    Times how long it takes to execute func(sequence, target).
    Returns milliseconds.
    """
    start = time.perf_counter()
    func(sequence, target, verbose=False)
    end = time.perf_counter()
    return (end - start) * 1000.0  # convert to ms


# -------------------------------------------------------------
#  Benchmark for a single N (used in Algorithm Comparison tab)
# -------------------------------------------------------------
def benchmark_searches(n: int = 10000) -> Dict[str, float]:
    """
    Benchmark linear vs binary search for a single input size.

    Returns a dictionary:
        {
          "linear_time_ms": ...,
          "binary_time_ms": ...,
          "linear_comparisons": ...,
          "binary_comparisons": ...
        }
    """
    # Create a sorted list of size n
    data = list(range(n))
    target = n - 1  # worst-case for linear (target at end)

    # Linear search
    t0 = time.perf_counter()
    _, lin_comps = linear_search(data, target, verbose=False)
    t1 = time.perf_counter()
    linear_ms = (t1 - t0) * 1000

    # Binary search
    t0 = time.perf_counter()
    _, _, bin_comps = binary_search(data, target, verbose=False)
    t1 = time.perf_counter()
    binary_ms = (t1 - t0) * 1000

    return {
        "linear_time_ms": linear_ms,
        "binary_time_ms": binary_ms,
        "linear_comparisons": lin_comps,
        "binary_comparisons": bin_comps,
    }


# -------------------------------------------------------------
#  Benchmark across many sizes (for line graphs)
# -------------------------------------------------------------
def compare_search_algorithms(
    sizes: List[int], target: int
) -> List[Tuple[int, float, float]]:
    """
    Run linear vs binary search for multiple input sizes.

    Returns a list of tuples:
        (n, linear_time_ms, binary_time_ms)
    """
    results = []

    for n in sizes:
        sequence = list(range(n))
        if target >= n:
            target = n - 1

        t_linear = time_function(linear_search, sequence, target)
        t_binary = time_function(binary_search, sequence, target)

        results.append((n, t_linear, t_binary))

    return results
