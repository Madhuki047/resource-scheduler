# src/algorithms/search_algorithms.py

sequence_a = [2, 3, 5, 7, 8, 10, 12, 15, 18, 20, 22]
item_a = 15


def linear_search(sequence, item, verbose=True):
    """
    Simple linear search.
    Returns (index_found or -1, comparisons)
    """
    comparisons = 0
    for index, value in enumerate(sequence):
        comparisons += 1
        if verbose:
            print(f"checking index {index}: {value}")
        if value == item:
            if verbose:
                print("found!")
            return index, comparisons
    if verbose:
        print("not found")
    return -1, comparisons


def binary_search(sequence, item, verbose=True):
    """
    Your binary search, extended to also give insertion index and comparison count.

    Returns:
        found_index (or -1 if not found),
        insertion_index (position where the item should go),
        comparisons
    """
    start_index = 0
    end_index = len(sequence) - 1
    comparisons = 0

    while start_index <= end_index:
        mid = (start_index + end_index) // 2
        value = sequence[mid]
        comparisons += 1

        if verbose:
            print(value)

        if value == item:
            if verbose:
                print(value == item)
            # if found, insertion index is same as mid
            return mid, mid, comparisons
        elif value < item:
            start_index = mid + 1  # search right half
            if verbose:
                print("new start", start_index)
        else:
            end_index = mid - 1    # search left half
            if verbose:
                print("new end", end_index)

    # not found: insertion point is start_index
    insertion_index = start_index
    if verbose:
        print("not found, insertion at", insertion_index)
    return -1, insertion_index, comparisons


if __name__ == "__main__":
    print("Linear search demo:")
    print(linear_search(sequence_a, item_a))

    print("\nBinary search demo:")
    print(binary_search(sequence_a, item_a))
