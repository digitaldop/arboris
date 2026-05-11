from django.core.exceptions import ValidationError
from django.core.cache import cache


def citta_choice_label(citta):
    """
    Testo per select/autocomplete. Tollera città con provincia mancante o non caricata
    (evita 500 in produzione con dati legacy o relazioni parziali).
    """
    if citta is None:
        return ""
    nome = getattr(citta, "nome", None) or ""
    prov = getattr(citta, "provincia", None)
    sigla = getattr(prov, "sigla", None) if prov is not None else None
    if sigla:
        return f"{nome} ({sigla})"
    return nome or str(getattr(citta, "pk", "")) or ""


def normalize_phone_number(value):
    raw_value = (value or "").strip()
    if not raw_value:
        return ""

    leading_plus = raw_value.startswith("+")
    digits = "".join(ch for ch in raw_value if ch.isdigit())

    if not digits:
        return ""

    return f"+{digits}" if leading_plus else digits


def validate_and_normalize_phone_number(value):
    raw_value = (value or "").strip()
    if not raw_value:
        return ""

    allowed_symbols = set(" +-/().")
    invalid_chars = [
        ch for ch in raw_value
        if not ch.isdigit() and ch not in allowed_symbols
    ]
    if invalid_chars:
        raise ValidationError("Inserisci un numero di telefono valido.")

    return normalize_phone_number(raw_value)


def _phone_display_format_from_settings():
    sentinel = object()
    try:
        from sistema.models import GENERAL_SETTINGS_CACHE_KEY, SistemaImpostazioniGenerali

        imp = cache.get(GENERAL_SETTINGS_CACHE_KEY, sentinel)
        if imp is sentinel:
            imp = SistemaImpostazioniGenerali.objects.first()
            cache.set(GENERAL_SETTINGS_CACHE_KEY, imp, 300)
        if imp and imp.formato_visualizzazione_telefono:
            return imp.formato_visualizzazione_telefono
    except Exception:  # noqa: BLE001
        pass
    return "it_plus_n3_2_2_3"


def _format_italian_local_10(ten: str, display_format: str) -> str:
    if len(ten) != 10 or not ten.isdigit():
        return ten
    if display_format == "it_plus_n3_3_2_2":
        return f"{ten[:3]} {ten[3:6]} {ten[6:8]} {ten[8:10]}"
    if display_format == "it_plus_n10":
        return ten
    return f"{ten[:3]} {ten[3:5]} {ten[5:7]} {ten[7:10]}"


def format_phone_number(value, display_format=None):
    """
    Visualizzazione. In archivio usare valori normalizzati senza spazi (normalize_phone_number / validate_...).
    """
    normalized = normalize_phone_number(value)
    if not normalized:
        return ""

    if display_format is None:
        display_format = _phone_display_format_from_settings()

    if normalized.startswith("+39") and len(normalized) == 13 and normalized[3:].isdigit() and len(normalized[3:]) == 10:
        formatted_local = _format_italian_local_10(normalized[3:], display_format)
        return f"+39 {formatted_local}"

    if len(normalized) == 10 and normalized.isdigit():
        return _format_italian_local_10(normalized, display_format)

    return normalized


def whatsapp_url_from_phone(value):
    normalized = normalize_phone_number(value)
    if not normalized:
        return ""

    digits = normalized.lstrip("+")
    if not digits:
        return ""

    return f"https://wa.me/{digits}"
