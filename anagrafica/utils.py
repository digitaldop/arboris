from django.core.exceptions import ValidationError


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


def format_phone_number(value):
    normalized = normalize_phone_number(value)
    if not normalized:
        return ""

    prefix = ""
    local_number = normalized

    if normalized.startswith("+39") and len(normalized[3:]) == 10:
        prefix = "+39"
        local_number = normalized[3:]

    if len(local_number) == 10 and local_number.isdigit():
        formatted_local = f"{local_number[:3]} {local_number[3:5]} {local_number[5:7]} {local_number[7:]}"
    else:
        formatted_local = local_number

    return f"{prefix} {formatted_local}".strip()


def whatsapp_url_from_phone(value):
    normalized = normalize_phone_number(value)
    if not normalized:
        return ""

    digits = normalized.lstrip("+")
    if not digits:
        return ""

    return f"https://wa.me/{digits}"
