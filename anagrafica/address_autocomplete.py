"""Authenticated proxy for Geoapify; no provider text creates territory records."""
import hashlib
import math
import re

import requests
import unicodedata
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .address_normalization import normalize_text
from .models import CAP, Citta, Indirizzo, Provincia

TOKEN_SALT = "anagrafica.geoapify.v1"


def territory_name(value):
    value = normalize_text(value)
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return re.sub(r"^(?:città metropolitana di|citta metropolitana di|provincia di|comune di)\s+", "", value)


def reconcile_territory(result):
    """Accept a unique municipality match, with province/CAP corroboration.

    No edit-distance matching: similar municipalities can be different places.
    Geoapify's county_code is a province abbreviation, never an ISTAT code.
    """
    code = str(result.get("county_code") or "").upper().removeprefix("IT-")
    province = Provincia.objects.filter(sigla=code).first() if len(code) == 2 else None
    if not province:
        name = territory_name(result.get("county"))
        matches = [p for p in Provincia.objects.all() if name and territory_name(p.nome) == name]
        province = matches[0] if len(matches) == 1 else None
    cities = Citta.objects.filter(attiva=True).select_related("provincia__regione")
    if province:
        cities = cities.filter(provincia=province)
    postcode = str(result.get("postcode") or "").strip()
    names = {territory_name(result.get(key)) for key in ("city", "town", "municipality", "village")}
    names.discard("")
    # Use database exact lookups first; only scan the narrowed territory for
    # accent/punctuation/provider-prefix differences.
    from django.db.models import Q
    exact = Q()
    for name in names:
        exact |= Q(nome__iexact=name)
    candidates = list(cities.filter(exact)) if names else []
    if not candidates:
        narrowed = cities
        if not province and postcode:
            narrowed = cities.filter(cap_list__codice=postcode, cap_list__attivo=True).distinct()
        candidates = [city for city in narrowed if territory_name(city.nome) in names]
    if len(candidates) > 1 and postcode:
        ids = set(CAP.objects.filter(codice=postcode, attivo=True).values_list("citta_id", flat=True))
        candidates = [city for city in candidates if city.pk in ids]
    if len(candidates) != 1:
        return None, None
    city = candidates[0]
    # A conflicting supplied province must never be ignored.
    if code and len(code) == 2 and city.provincia.sigla != code:
        return None, None
    cap = CAP.objects.filter(citta=city, codice=postcode, attivo=True).first() if postcode else None
    return city, cap


def address_payload(address):
    city = address.citta
    return {
        "id": address.pk, "source": "arboris", "label": address.label_full(),
        "via": address.via, "numero_civico": address.numero_civico,
        "citta_id": address.citta_id, "citta_label": str(city) if city else "",
        "cap_id": address.cap_scelto_id, "cap": address.cap,
        "provincia": city.provincia.nome if city else "",
        "regione": str(city.provincia.regione or "") if city else "",
    }


def provider_payload(result):
    if not isinstance(result, dict) or str(result.get("country_code", "")).lower() != "it":
        return None
    via = str(result.get("street") or "").strip()
    number = str(result.get("housenumber") or "").strip()
    if not via or len(via) > 200 or len(number) > 20:
        return None
    city, cap = reconcile_territory(result)
    payload = {
        "source": "geoapify", "label": str(result.get("formatted") or f"{via} {number}")[:500],
        "via": via, "numero_civico": number,
        "citta_id": city.pk if city else None, "citta_label": str(city) if city else "",
        "cap_id": cap.pk if cap else None, "cap": str(result.get("postcode") or "")[:10],
        "provincia": city.provincia.nome if city else str(result.get("county") or "")[:100],
        "regione": str(city.provincia.regione or "") if city else str(result.get("state") or "")[:100],
        "requires_review": not city or not cap,
    }
    metadata = {"geoapify_place_id": str(result.get("place_id") or "")[:512]}
    for source, target, bound in (("lat", "latitudine", 90), ("lon", "longitudine", 180)):
        try:
            coordinate = float(result[source])
            if not math.isfinite(coordinate) or abs(coordinate) > bound:
                return None
            metadata[target] = f"{coordinate:.7f}"
        except (KeyError, TypeError, ValueError):
            metadata[target] = None
    payload["token"] = signing.dumps({"address": {k: payload[k] for k in ("via", "numero_civico", "citta_id", "cap_id")}, "metadata": metadata}, salt=TOKEN_SALT)
    return payload


@require_GET
def address_autocomplete(request):
    query = " ".join(request.GET.get("q", "").split())
    if len(query) > 200 or any(ord(char) < 32 for char in query):
        return JsonResponse({"results": [], "error": "Ricerca non valida."}, status=400)
    if len(query) < 4:
        return JsonResponse({"results": []})
    city_id = request.GET.get("citta_id", "")
    if city_id and (not city_id.isdigit() or len(city_id) > 12):
        return JsonResponse({"results": [], "error": "Comune non valido."}, status=400)
    city = Citta.objects.select_related("provincia").filter(pk=city_id, attiva=True).first() if city_id else None
    if city_id and city is None:
        return JsonResponse({"results": [], "error": "Comune non valido."}, status=400)
    local = Indirizzo.objects.select_related("citta__provincia__regione", "cap_scelto", "provincia")
    if city:
        local = local.filter(citta=city)
    for word in normalize_text(query).split():
        from django.db.models import Q
        local = local.filter(Q(via_normalizzata__contains=word) | Q(civico_normalizzato__icontains=word) | Q(citta__nome__icontains=word) | Q(cap__contains=word))
    results = [address_payload(a) for a in local.order_by("pk")[:5]]
    if not settings.GEOAPIFY_API_KEY:
        return JsonResponse({"results": results, "unavailable": True})
    text = f"{query}, {city.nome} ({city.provincia.sigla})" if city else query
    cache_key = "address-autocomplete:" + hashlib.sha256(text.casefold().encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"results": results + cached})
    rate_key = f"address-autocomplete-rate:{request.user.pk}"
    cache.add(rate_key, 0, timeout=60)
    try:
        count = cache.incr(rate_key)
    except ValueError:
        count = 1
        cache.set(rate_key, count, timeout=60)
    if count > 30:
        return JsonResponse({"results": results, "unavailable": True}, status=429)
    try:
        response = requests.get(
            "https://api.geoapify.com/v1/geocode/autocomplete",
            params={"text": text, "filter": "countrycode:it", "lang": "it", "format": "json", "limit": 5, "apiKey": settings.GEOAPIFY_API_KEY},
            timeout=(2, 4),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("Invalid provider response")
        suggestions = [payload for row in data["results"][:5] if (payload := provider_payload(row))]
    except (requests.RequestException, ValueError, TypeError):
        # Never log exception URLs: requests includes the secret API key.
        return JsonResponse({"results": results, "unavailable": True})
    cache.set(cache_key, suggestions, timeout=120)
    return JsonResponse({"results": results + suggestions})
