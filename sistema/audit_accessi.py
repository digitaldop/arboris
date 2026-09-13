"""Registra le pagine HTML aperte dagli utenti autenticati."""

from .audit import format_audit_user_label, is_audit_disabled, normalize_audit_user
from .models import AzioneOperazioneCronologia, ModuloOperazioneCronologia
from .signals import save_audit_entry


def log_page_view(request, response):
    user = normalize_audit_user(getattr(request, "user", None))
    if user is None or is_audit_disabled() or request.method != "GET":
        return
    if response.status_code != 200 or response.streaming:
        return
    if response.get("Content-Type", "").split(";", 1)[0].strip().lower() != "text/html":
        return
    if response.get("Content-Disposition"):
        return
    # Fetch, aggiornamenti dei menu e frammenti HTML non sono visite a pagine.
    if request.headers.get("Sec-Fetch-Dest", "document") not in {"document", "iframe"}:
        return
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("HX-Request") == "true":
        return
    if "prefetch" in (request.headers.get("Purpose", "") + request.headers.get("Sec-Purpose", "")).lower():
        return

    match = getattr(request, "resolver_match", None)
    if match is None or not match.url_name:
        return
    # Richiediamo un documento completo anche per client privi di Fetch Metadata.
    if b"<html" not in response.content[:1024].lower():
        return

    app_label = match.func.__module__.split(".", 1)[0]
    modulo = {
        "osservazioni": "anagrafica",
        "archivio_storico": "anagrafica",
        "fondo_accantonamento": "economia",
    }.get(app_label, app_label)
    if modulo not in ModuloOperazioneCronologia.values:
        modulo = ModuloOperazioneCronologia.SISTEMA
    if match.url_name == "home":
        modulo = ModuloOperazioneCronologia.SISTEMA

    # Il percorso identifica anche la scheda consultata. Query string, contenuti
    # della pagina, credenziali e identificativi di sessione non vengono salvati.
    page_label = match.url_name.replace("_", " ").capitalize()
    save_audit_entry(
        azione=AzioneOperazioneCronologia.VISUALIZZAZIONE,
        modulo=modulo,
        utente=user,
        utente_label=format_audit_user_label(user),
        app_label=app_label[:60],
        model_name="pagina",
        model_verbose_name="Pagina",
        oggetto_label=page_label[:255],
        descrizione=f"Visualizzata pagina: {page_label} ({request.path}).",
    )
