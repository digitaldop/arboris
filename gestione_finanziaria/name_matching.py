"""Confronti testuali per suggerimenti da confermare, mai per automatismi."""

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache


def normalize_name(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


@lru_cache(maxsize=4096)
def phrase_similarity(name, text):
    """Cerca parole intere contigue, tollerando spazi e piccoli refusi.

    Confrontare finestre di parole evita che Alfa corrisponda ad Alfabeta.
    Il limite minimo evita somiglianze casuali fra sigle o nomi brevi.
    """
    name_tokens = normalize_name(name).split()
    text_tokens = normalize_name(text).split()
    compact_name = "".join(name_tokens)
    if len(compact_name) < 5:
        return 0.0
    best = 0.0
    for start in range(len(text_tokens)):
        for size in range(max(1, len(name_tokens) - 1), len(name_tokens) + 3):
            tokens = text_tokens[start:start + size]
            compact = "".join(tokens)
            if not compact or abs(len(compact) - len(compact_name)) > max(1, len(compact_name) // 6):
                continue
            if compact == compact_name:
                return 1.0 if tokens == name_tokens else 0.98
            similarity = SequenceMatcher(None, compact_name, compact, autojunk=False).ratio()
            if similarity >= 0.86:
                best = max(best, similarity)
    return best


def person_similarity(nome, cognome, text):
    normalized_text = normalize_name(text)

    def part_similarity(value):
        normalized = normalize_name(value)
        if normalized and f" {normalized} " in f" {normalized_text} ":
            return 1.0
        return phrase_similarity(value, text)

    given_similarity = part_similarity(nome)
    surname_similarity = part_similarity(cognome)
    full_name = " ".join(filter(None, (nome, cognome)))
    similarity = max(
        phrase_similarity(full_name, text),
        phrase_similarity(" ".join(filter(None, (cognome, nome))), text),
    ) if given_similarity and surname_similarity else 0.0
    reason = "Nominativo simile"
    # Un nome composto può comparire senza cognome: è un indizio più debole.
    if len(normalize_name(nome).split()) >= 2:
        if given_similarity and given_similarity * 0.86 > similarity:
            similarity = given_similarity * 0.86
            reason = "Nome composto compatibile, cognome da verificare"
    return similarity, reason


SUPPLIER_GENERIC_WORDS = {
    "srls", "srl", "spa", "sas", "snc", "societa", "cooperativa", "ditta",
    "impresa", "servizi", "service", "services", "soc", "coop", "sede",
}


def supplier_similarity(denominazione, text):
    words = [word for word in normalize_name(denominazione).split()
             if len(word) >= 4 and word not in SUPPLIER_GENERIC_WORDS]
    if not words:
        return 0.0
    # Una parola distintiva (es. Gjata) resta riconoscibile nella ragione sociale.
    significant_text = " ".join(word for word in normalize_name(text).split()
                                if word not in SUPPLIER_GENERIC_WORDS and len(word) > 2)
    full = phrase_similarity(" ".join(words), significant_text)
    partial = max((phrase_similarity(word, text) for word in words if len(word) >= 5), default=0.0)
    return max(full, partial * 0.88)
