"""Feature engineering parameters: section maps, weights, similarity knobs."""

ITEM_SECTIONS = [
    "item_1",
    "item_1a",
    "item_1b",
    "item_1c",
    "item_2",
    "item_3",
    "item_4",
    "item_5",
    "item_6",
    "item_7",
    "item_7a",
    "item_8",
    "item_9",
    "item_9a",
    "item_9b",
    "item_10",
    "item_11",
    "item_12",
    "item_13",
    "item_14",
    "item_15",
]

# Per-section importance weights for the weighted change_intensity calculation.
# Inspired by the LazyPrices paper: MD&A, Risk Factors, and Business are the
# strongest predictors of post-filing drift. Sections absent from this dict
# are ignored (weight 0). The weighted average divides by the sum of weights
# for sections actually present, so missing sections don't penalise the score.
SECTION_WEIGHTS = {
    "item_1":  0.15,   # Business
    "item_1a": 0.25,   # Risk Factors
    "item_1b": 0.02,   # Unresolved Staff Comments
    "item_1c": 0.02,   # Cybersecurity
    "item_2":  0.02,   # Properties
    "item_3":  0.01,   # Legal Proceedings
    "item_4":  0.01,   # Mine Safety Disclosures
    "item_5":  0.02,   # Market for Common Equity
    "item_6":  0.01,   # Reserved
    "item_7":  0.30,   # MD&A (strongest predictor)
    "item_7a": 0.10,   # Quantitative & Qualitative Market Risk
    "item_8":  0.05,   # Financial Statements
    "item_9":  0.01,   # Accountant Changes / Disagreements
    "item_9a": 0.02,   # Controls and Procedures
    "item_9b": 0.01,   # Other Information
    "item_10": 0.01,   # Directors / Corporate Governance
    "item_11": 0.01,   # Executive Compensation
    "item_12": 0.01,   # Security Ownership
    "item_13": 0.01,   # Related Transactions
    "item_14": 0.01,   # Principal Accountant Fees
    "item_15": 0.01,   # Exhibits / Financial Statement Schedules
}

# 10-Q sections (Part I and Part II items). The regex in extract_clean.py
# already matches these patterns; this list is used for section-level LAS.
ITEM_SECTIONS_10Q = [
    "item_1",   # Financial Statements
    "item_2",   # MD&A
    "item_3",   # Quantitative & Qualitative Market Risk
    "item_4",   # Controls and Procedures
    "item_1a",  # Risk Factors (Part II)
    "item_2",   # Unregistered Sales of Equity
    "item_5",   # Other Information
    "item_6",   # Exhibits
]

# Section weights for 10-Q filings (same key sections, fewer sections total).
SECTION_WEIGHTS_10Q = {
    "item_1":  0.10,   # Financial Statements
    "item_2":  0.35,   # MD&A (strongest predictor, same as 10-K item_7)
    "item_3":  0.15,   # Quantitative & Qualitative Market Risk
    "item_4":  0.05,   # Controls and Procedures
    "item_1a": 0.30,   # Risk Factors
    "item_5":  0.03,   # Other Information
    "item_6":  0.02,   # Exhibits
}

SIMILARITY_MEASURES = ["cosine", "jaccard"]

NUMERIC_TABLE_THRESHOLD = 0.15

# Weight of text-based similarity in the hybrid change_intensity formula.
# change_intensity = alpha * text_change + (1 - alpha) * numerical_divergence
NUMERIC_CHANGE_ALPHA = 0.7
