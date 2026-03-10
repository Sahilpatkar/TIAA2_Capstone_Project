"""
Build term-frequency (count) vectors and optional TF-IDF vectors for
cleaned 10-K filings.  Vectors are stored as sparse .npz files keyed by
(cik, accession, section_id).

Usage:
    python embeddings.py --entity-dir "Apple Inc._0000320193"
"""

import argparse
import json
import os
import re

import nltk
import numpy as np
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

import config

# Best-effort NLTK data download; SSL issues on some systems are non-fatal.
for _pkg in ("stopwords", "wordnet", "omw-1.4"):
    try:
        nltk.download(_pkg, quiet=True)
    except Exception:
        pass

_word_re = re.compile(r"[a-z]{2,}")

_FALLBACK_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "shall", "should", "may", "might", "must", "can", "could", "not", "no",
    "nor", "so", "if", "then", "than", "too", "very", "just", "about",
    "above", "after", "again", "all", "also", "am", "any", "because",
    "before", "below", "between", "both", "during", "each", "few", "further",
    "get", "got", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "i", "into", "it", "its", "itself", "me", "more", "most",
    "my", "myself", "now", "only", "other", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "some", "such", "that", "their",
    "theirs", "them", "themselves", "these", "they", "this", "those",
    "through", "under", "until", "up", "us", "we", "what", "when", "where",
    "which", "while", "who", "whom", "why", "you", "your", "yours",
    "yourself", "yourselves",
}


def _get_stop_words() -> set:
    try:
        return set(stopwords.words("english"))
    except LookupError:
        return _FALLBACK_STOPWORDS


def _get_lemmatizer():
    try:
        lem = WordNetLemmatizer()
        lem.lemmatize("test", pos="v")  # trigger lazy load
        return lem
    except LookupError:
        return None


_stop_words = _get_stop_words()
_lemmatizer = _get_lemmatizer()


# ---------------------------------------------------------------------------
# Text pre-processing (aligned with PythonPractice10 notebook)
# ---------------------------------------------------------------------------

def tokenize_and_lemmatize(text: str, remove_stopwords: bool = True) -> str:
    """Lowercase, tokenize, lemmatize, optionally drop stopwords.
    Returns a single space-joined string ready for sklearn vectorizers."""
    tokens = _word_re.findall(text.lower())
    if _lemmatizer is not None:
        tokens = [_lemmatizer.lemmatize(t, pos="v") for t in tokens]
    if remove_stopwords:
        tokens = [t for t in tokens if t not in _stop_words]
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Loading cleaned data
# ---------------------------------------------------------------------------

def load_cleaned_filings(entity_dir: str) -> list[dict]:
    """Load all *_cleaned.json files under entity_dir/cleaned/."""
    cleaned_dir = os.path.join(entity_dir, "cleaned")
    if not os.path.isdir(cleaned_dir):
        return []

    filings = []
    for fname in sorted(os.listdir(cleaned_dir)):
        if not fname.endswith("_cleaned.json"):
            continue
        path = os.path.join(cleaned_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["_path"] = path
        data["_basename"] = fname.replace("_cleaned.json", "")
        filings.append(data)
    return filings


# ---------------------------------------------------------------------------
# Vectorisation
# ---------------------------------------------------------------------------

def build_vectors(
    entity_dir: str,
    use_tfidf: bool = False,
    remove_stopwords: bool = True,
) -> dict:
    """
    Build count (or TF-IDF) vectors for all cleaned filings in an entity dir.

    Returns a dict with:
        "vectorizer": fitted sklearn vectorizer
        "doc_vectors": {basename: sparse matrix (1 x vocab)}
        "section_vectors": {basename: {section_key: sparse matrix (1 x vocab)}}
        "vocab": list of feature names
    """
    filings = load_cleaned_filings(entity_dir)
    if not filings:
        raise FileNotFoundError(f"No cleaned filings in {entity_dir}/cleaned/")

    all_texts: list[str] = []
    text_labels: list[tuple[str, str | None]] = []  # (basename, section_key_or_None)

    for filing in filings:
        processed = tokenize_and_lemmatize(filing["full_text"], remove_stopwords)
        all_texts.append(processed)
        text_labels.append((filing["_basename"], None))

        for sec_key, sec_text in filing.get("sections", {}).items():
            processed_sec = tokenize_and_lemmatize(sec_text, remove_stopwords)
            all_texts.append(processed_sec)
            text_labels.append((filing["_basename"], sec_key))

    VectorizerClass = TfidfVectorizer if use_tfidf else CountVectorizer
    vectorizer = VectorizerClass(max_features=50_000)
    matrix = vectorizer.fit_transform(all_texts)

    doc_vectors: dict[str, sparse.spmatrix] = {}
    section_vectors: dict[str, dict[str, sparse.spmatrix]] = {}

    for idx, (basename, sec_key) in enumerate(text_labels):
        vec = matrix[idx]
        if sec_key is None:
            doc_vectors[basename] = vec
        else:
            section_vectors.setdefault(basename, {})[sec_key] = vec

    return {
        "vectorizer": vectorizer,
        "doc_vectors": doc_vectors,
        "section_vectors": section_vectors,
        "vocab": vectorizer.get_feature_names_out().tolist(),
    }


def save_vectors(entity_dir: str, vectors_result: dict) -> str:
    """Persist vectors as .npz files under data/vectors/<entity_dir_basename>/."""
    entity_basename = os.path.basename(entity_dir)
    out_dir = os.path.join(config.VECTORS_DIR, entity_basename)
    os.makedirs(out_dir, exist_ok=True)

    for basename, vec in vectors_result["doc_vectors"].items():
        path = os.path.join(out_dir, f"{basename}_doc.npz")
        sparse.save_npz(path, vec)

    for basename, sec_dict in vectors_result["section_vectors"].items():
        for sec_key, vec in sec_dict.items():
            path = os.path.join(out_dir, f"{basename}_{sec_key}.npz")
            sparse.save_npz(path, vec)

    vocab_path = os.path.join(out_dir, "vocab.json")
    with open(vocab_path, "w") as f:
        json.dump(vectors_result["vocab"], f)

    print(f"  Vectors saved to {out_dir}")
    return out_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build TF / TF-IDF vectors for cleaned 10-K text")
    parser.add_argument("--entity-dir", required=True, help="Path to entityName_cik folder")
    parser.add_argument("--tfidf", action="store_true", help="Use TF-IDF instead of raw counts")
    args = parser.parse_args()

    result = build_vectors(args.entity_dir, use_tfidf=args.tfidf)
    save_vectors(args.entity_dir, result)
    print(f"Vocab size: {len(result['vocab'])}, Documents: {len(result['doc_vectors'])}")


if __name__ == "__main__":
    main()
