"""
Extract financial numbers from 10-K text and compute a numerical divergence
score between two filing texts.

The divergence score captures year-over-year changes in dollar amounts,
percentages, and large bare numbers that bag-of-words text similarity
completely misses (the tokenizer strips all digits).

Usage:
    from numeric_change import compute_numerical_divergence
    score = compute_numerical_divergence(current_text, prior_text)
    # score in [0, 1]; 0 = identical numbers, 1 = extreme divergence
"""

import math
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Regex patterns for financial numbers
# ---------------------------------------------------------------------------

# "$5.3 billion", "$140.8 million", "$10,000", "$97.3 billion"
_DOLLAR_RE = re.compile(
    r"\$\s*([\d,]+\.?\d*)\s*(billion|million|thousand|bn|mn|mm)?",
    re.IGNORECASE,
)

# "12.5%", "3%"
_PERCENT_RE = re.compile(
    r"([\d,]+\.?\d*)\s*%",
)

# Bare large numbers with commas: "140,800", "5,300,000"
# At least one comma required to distinguish from page/section numbers.
_BARE_LARGE_RE = re.compile(
    r"(?<![.\d$])(\d{1,3}(?:,\d{3})+(?:\.\d+)?)(?![%\d])",
)

_MULTIPLIERS = {
    "billion": 1e9, "bn": 1e9,
    "million": 1e6, "mn": 1e6, "mm": 1e6,
    "thousand": 1e3,
}

# Noise filters
_YEAR_RANGE = range(1990, 2036)
_NOISE_PREFIX_RE = re.compile(
    r"(?:item|page|part|exhibit|schedule|footnote|note)\s*$",
    re.IGNORECASE,
)
_ACCESSION_RE = re.compile(r"\d{10,}")


def _parse_comma_number(s: str) -> float:
    """Parse a string like '140,800.5' into a float."""
    return float(s.replace(",", ""))


def _context_window(text: str, start: int, end: int, n_words: int = 10) -> set[str]:
    """Return a set of up to *n_words* lowercase alpha tokens surrounding
    the span [start, end) in *text*."""
    before = text[max(0, start - 300):start]
    after = text[end:end + 300]
    words_before = re.findall(r"[a-z]{2,}", before.lower())[-n_words:]
    words_after = re.findall(r"[a-z]{2,}", after.lower())[:n_words]
    return set(words_before + words_after)


def _is_noise(text: str, start: int, value: float) -> bool:
    """Return True if the number at *start* looks like a year, page number,
    section reference, or accession fragment."""
    if value == int(value) and int(value) in _YEAR_RANGE:
        return True
    prefix = text[max(0, start - 30):start].rstrip()
    if _NOISE_PREFIX_RE.search(prefix):
        return True
    if _ACCESSION_RE.match(text[start:start + 20]):
        return True
    return False


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_financial_numbers(text: str) -> list[dict]:
    """Extract financial numbers from *text*.

    Returns a list of dicts with keys:
        value    – normalised float
        position – character offset in the original text
        context  – set of surrounding words for matching
        raw      – the matched substring
    """
    if not text:
        return []

    results: list[dict] = []
    seen_positions: set[int] = set()

    # Dollar amounts (highest priority — most unambiguous)
    for m in _DOLLAR_RE.finditer(text):
        raw_num = m.group(1)
        multiplier_str = (m.group(2) or "").lower()
        value = _parse_comma_number(raw_num)
        multiplier = _MULTIPLIERS.get(multiplier_str, 1.0)
        value *= multiplier

        if value == 0:
            continue
        if _is_noise(text, m.start(), value):
            continue

        results.append({
            "value": value,
            "position": m.start(),
            "context": _context_window(text, m.start(), m.end()),
            "raw": m.group(0),
        })
        seen_positions.add(m.start())

    # Percentages
    for m in _PERCENT_RE.finditer(text):
        if m.start() in seen_positions:
            continue
        value = _parse_comma_number(m.group(1))
        if _is_noise(text, m.start(), value):
            continue

        results.append({
            "value": value,
            "position": m.start(),
            "context": _context_window(text, m.start(), m.end()),
            "raw": m.group(0),
        })
        seen_positions.add(m.start())

    # Bare large numbers (with commas)
    for m in _BARE_LARGE_RE.finditer(text):
        if m.start() in seen_positions:
            continue
        value = _parse_comma_number(m.group(1))
        if value == 0:
            continue
        if _is_noise(text, m.start(), value):
            continue

        results.append({
            "value": value,
            "position": m.start(),
            "context": _context_window(text, m.start(), m.end()),
            "raw": m.group(1),
        })
        seen_positions.add(m.start())

    results.sort(key=lambda r: r["position"])
    return results


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _jaccard(s1: set, s2: set) -> float:
    if not s1 and not s2:
        return 1.0
    union = s1 | s2
    if not union:
        return 0.0
    return len(s1 & s2) / len(union)


def match_numbers(
    nums_current: list[dict],
    nums_prior: list[dict],
    min_context_sim: float = 0.15,
) -> list[tuple[dict, dict]]:
    """Match extracted numbers between current and prior texts.

    Uses context-word Jaccard similarity to pair numbers.  Each number is
    matched at most once (greedy best-first).  Pairs below *min_context_sim*
    are discarded.
    """
    if not nums_current or not nums_prior:
        return []

    # Build all candidate pairs with context similarity
    candidates: list[tuple[float, int, int]] = []
    for i, nc in enumerate(nums_current):
        for j, np_ in enumerate(nums_prior):
            sim = _jaccard(nc["context"], np_["context"])
            if sim >= min_context_sim:
                candidates.append((sim, i, j))

    # Greedy matching: highest similarity first
    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_cur: set[int] = set()
    used_pri: set[int] = set()
    pairs: list[tuple[dict, dict]] = []

    for sim, i, j in candidates:
        if i in used_cur or j in used_pri:
            continue
        pairs.append((nums_current[i], nums_prior[j]))
        used_cur.add(i)
        used_pri.add(j)

    return pairs


# ---------------------------------------------------------------------------
# Divergence score
# ---------------------------------------------------------------------------

def _log_ratio(v_new: float, v_old: float) -> float:
    """Symmetric log-ratio: |ln(v_new / v_old)|.
    Both values must be positive (enforced by caller)."""
    if v_old == 0 or v_new == 0:
        return 0.0
    return abs(math.log(v_new / v_old))


def _squash(x: float, k: float = 2.0) -> float:
    """Sigmoid-like squash: maps [0, inf) -> [0, 1).
    k controls steepness; k=2 means a 7x change (~ln 7 ≈ 1.95) maps to ~0.5."""
    return 2.0 / (1.0 + math.exp(-x / k)) - 1.0


def compute_numerical_divergence(
    text_current: str,
    text_prior: str,
) -> float:
    """Compute a numerical divergence score in [0, 1] between two texts.

    Returns 0.0 when no matchable numbers exist in either text.
    """
    nums_cur = extract_financial_numbers(text_current)
    nums_pri = extract_financial_numbers(text_prior)

    if not nums_cur and not nums_pri:
        return 0.0

    pairs = match_numbers(nums_cur, nums_pri)
    if not pairs:
        # Numbers exist but none matched — treat as moderate divergence
        n_total = len(nums_cur) + len(nums_pri)
        if n_total == 0:
            return 0.0
        return _squash(1.0)

    ratios: list[float] = []
    for nc, np_ in pairs:
        v_new = abs(nc["value"])
        v_old = abs(np_["value"])
        if v_new > 0 and v_old > 0:
            ratios.append(_log_ratio(v_new, v_old))

    if not ratios:
        return 0.0

    mean_ratio = sum(ratios) / len(ratios)
    return _squash(mean_ratio)
