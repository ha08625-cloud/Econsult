"""Canonical text normalisation for the synthetic fragment tooling.

This module holds the *only* definition of normalisation used anywhere in the
recombination pipeline. It is load-bearing three times over -- it produces the
deduplication key, the fragment ID hash input, and the split key -- so two
divergent implementations would produce two different datasets from the same
libraries. Nothing else may reimplement it.

Normalisation is used for keys only. It is never applied to emitted text: the
encoder receives raw, unmodified user input at runtime, so laundering casing,
contractions or typos at generation time would train on a distribution the
encoder never sees.
"""

from __future__ import annotations

import re
import unicodedata

# NFKC does not fold typographic punctuation to ASCII, and the libraries mix
# straight and curly apostrophes for the same sentence ("I've" / "I’ve").
# Without this step the same text normalises two ways.
_PUNCTUATION_FOLD = {
    ord("‘"): "'",  # left single quotation mark
    ord("’"): "'",  # right single quotation mark
    ord("“"): '"',  # left double quotation mark
    ord("”"): '"',  # right double quotation mark
    ord("–"): "-",  # en dash
    ord("—"): "-",  # em dash
}

_WHITESPACE_RUN = re.compile(r"\s+")

# Trailing terminal punctuation, plus any whitespace tangled up in it, so that
# "I had a fever." and "I had a fever ." collapse to the same key.
_TRAILING_TERMINATORS = re.compile(r"[.!?\s]+$")


def normalise(text: str) -> str:
    """Return the canonical key form of ``text``.

    The steps, in order:

    1. Unicode NFKC.
    2. Fold typographic quotes and dashes to ASCII.
    3. Case-fold.
    4. Collapse whitespace runs to a single space and strip.
    5. Strip trailing ``.``, ``!`` and ``?``.
    """
    result = unicodedata.normalize("NFKC", text)
    result = result.translate(_PUNCTUATION_FOLD)
    result = result.casefold()
    result = _WHITESPACE_RUN.sub(" ", result).strip()
    return _TRAILING_TERMINATORS.sub("", result)
