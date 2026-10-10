import math
from bisect import bisect_right


def decimal_odds(odds):
    odds = float(odds)
    if not math.isfinite(odds) or abs(odds) < 100:
        raise ValueError("A usable American price must have magnitude at least 100.")
    return 1 + (odds / 100 if odds > 0 else 100 / abs(odds))


def break_even(odds):
    return 1 / decimal_odds(odds)


def ev(probability, odds):
    return float(probability) * decimal_odds(odds) - 1


def kelly(probability, odds):
    return max(0., ev(probability, odds) / (decimal_odds(odds) - 1))


def bucket(odds, config):
    odds = float(odds)
    if odds < 0:
        return "Negative odds"
    edges = config.price_breaks
    index = bisect_right(edges, odds)
    if index == 0:
        return f"Below +{edges[0]:g}"
    if index == len(edges):
        return f"+{edges[-1]:g}+"
    return f"+{edges[index-1]:g} to <+{edges[index]:g}"
