"""numpy.unique(axis=0) for rows of small non-negative integers, fast.

unique(axis=0) sorts rows through a structured view, which on the edge list
of a stick model (tens of millions of rows) took longer than the rest of the
check put together. Packing each row into one int64, with the first column
most significant, gives the same lexicographic order, so the result is
identical and comes from a plain 1-D sort.
"""

from numpy import asarray, int64, unique


def unique_rows(rows, return_inverse=False, return_counts=False):
    """Same results as numpy.unique(rows, axis=0, ...) for an (n, k) array
    of non-negative integers whose packed key fits in 63 bits."""
    rows = asarray(rows)
    if len(rows) == 0 or rows.ndim != 2:
        return unique(rows, axis=0, return_inverse=return_inverse,
                      return_counts=return_counts)
    radix = [int(rows[:, j].max()) + 1 for j in range(rows.shape[1])]
    span = 1
    for r in radix:
        span *= r
    if span >= 2 ** 63:
        return unique(rows, axis=0, return_inverse=return_inverse,
                      return_counts=return_counts)

    key = rows[:, 0].astype(int64)
    for j in range(1, rows.shape[1]):
        key = key * radix[j] + rows[:, j]
    _, first, *rest = unique(key, return_index=True,
                             return_inverse=return_inverse,
                             return_counts=return_counts)
    out = [rows[first]]
    if return_inverse:
        out.append(rest.pop(0).ravel())
    if return_counts:
        out.append(rest.pop(0))
    return out[0] if len(out) == 1 else tuple(out)
