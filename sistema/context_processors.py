from django.db.utils import OperationalError, ProgrammingError

from .models import LivelloPermesso, Scuola, SistemaImpostazioniGenerali, get_site_font_settings
from .permissions import (
    get_user_permission_profile,
    user_can_access_database_backups,
    user_has_module_permission,
    user_is_operational_admin,
)
from .terminology import get_student_terminology


def get_current_permission_module(request):
    resolver_match = getattr(request, "resolver_match", None)
    if not resolver_match or not getattr(resolver_match, "func", None):
        return ""

    view_module = getattr(resolver_match.func, "__module__", "")
    if view_module.startswith("anagrafica."):
        return "anagrafica"
    if view_module.startswith("economia."):
        return "economia"
    if view_module.startswith("calendario."):
        return "calendario"
    if view_module.startswith("servizi_extra."):
        return "servizi_extra"
    if view_module.startswith("gestione_finanziaria."):
        return "gestione_finanziaria"
    if view_module.startswith("gestione_amministrativa."):
        return "gestione_amministrativa"
    if view_module.startswith("sistema."):
        return "sistema"
    if getattr(request, "path", "").startswith(("/scuola/calendario/", "/calendario/")):
        return "calendario"
    return ""


def scuola_context(request):
    scuola = (
        Scuola.objects.select_related(
            "indirizzo_sede_legale__citta__provincia",
            "indirizzo_operativo__citta__provincia",
        )
        .prefetch_related("telefoni", "email")
        .first()
    )

    return {
        "scuola_header": scuola,
    }


def general_settings_context(request):
    try:
        general_settings = SistemaImpostazioniGenerali.objects.first()
    except (OperationalError, ProgrammingError):
        general_settings = None

    return {
        "general_settings": general_settings,
        "site_fonts": get_site_font_settings(general_settings),
        "student_terminology": get_student_terminology(
            getattr(general_settings, "terminologia_studente", None)
        ),
    }


def get_current_servizio_extra_id(request):
    servizio_id = request.GET.get("servizio") or ""
    if servizio_id.isdigit():
        return int(servizio_id)

    resolver_match = getattr(request, "resolver_match", None)
    if not resolver_match:
        return None

    url_name = getattr(resolver_match, "url_name", "") or ""
    kwargs = getattr(resolver_match, "kwargs", {}) or {}
    pk = kwargs.get("pk")

    if url_name in {
        "dettaglio_servizio_extra",
        "modifica_servizio_extra",
        "elimina_servizio_extra",
    } and pk:
        return int(pk)

    try:
        from servizi_extra.models import (
            IscrizioneServizioExtra,
            RataServizioExtra,
            ServizioExtra,
            TariffaServizioExtra,
        )
    except (OperationalError, ProgrammingError):
        return None

    if url_name in {"modifica_tariffa_servizio_extra", "elimina_tariffa_servizio_extra"} and pk:
        return TariffaServizioExtra.objects.filter(pk=pk).values_list("servizio_id", flat=True).first()

    if url_name in {
        "modifica_iscrizione_servizio_extra",
        "elimina_iscrizione_servizio_extra",
        "ricalcola_rate_iscrizione_servizio_extra",
    } and pk:
        return IscrizioneServizioExtra.objects.filter(pk=pk).values_list("servizio_id", flat=True).first()

    if url_name == "modifica_rata_servizio_extra" and pk:
        return (
            RataServizioExtra.objects.filter(pk=pk)
            .values_list("iscrizione__servizio_id", flat=True)
            .first()
        )

    iscrizione_id = request.GET.get("iscrizione") or ""
    if url_name == "lista_rate_servizi_extra" and iscrizione_id.isdigit():
        return IscrizioneServizioExtra.objects.filter(pk=iscrizione_id).values_list("servizio_id", flat=True).first()

    if url_name in {
        "lista_servizi_extra",
        "lista_tariffe_servizi_extra",
        "lista_iscrizioni_servizi_extra",
        "lista_rate_servizi_extra",
        "crea_servizio_extra",
        "crea_tariffa_servizio_extra",
        "crea_iscrizione_servizio_extra",
    }:
        return None

    if current_module := get_current_permission_module(request):
        if current_module != "servizi_extra":
            return None

    return ServizioExtra.objects.filter(pk=pk).values_list("pk", flat=True).first() if pk else None


def sistema_permissions_context(request):
    user = getattr(request, "user", None)
    profilo = get_user_permission_profile(user)
    current_module = get_current_permission_module(request)
    can_view_anagrafica = user_has_module_permission(user, "anagrafica", LivelloPermesso.VISUALIZZAZIONE)
    can_manage_anagrafica = user_has_module_permission(user, "anagrafica", LivelloPermesso.GESTIONE)
    can_view_economia = user_has_module_permission(user, "economia", LivelloPermesso.VISUALIZZAZIONE)
    can_manage_economia = user_has_module_permission(user, "economia", LivelloPermesso.GESTIONE)
    can_view_sistema = user_has_module_permission(user, "sistema", LivelloPermesso.VISUALIZZAZIONE)
    can_manage_sistema = user_has_module_permission(user, "sistema", LivelloPermesso.GESTIONE)
    can_view_calendario = user_has_module_permission(user, "calendario", LivelloPermesso.VISUALIZZAZIONE)
    can_manage_calendario = user_has_module_permission(user, "calendario", LivelloPermesso.GESTIONE)
    can_view_servizi_extra = user_has_module_permission(user, "servizi_extra", LivelloPermesso.VISUALIZZAZIONE)
    can_manage_servizi_extra = user_has_module_permission(user, "servizi_extra", LivelloPermesso.GESTIONE)
    can_view_gestione_finanziaria = user_has_module_permission(
        user,
        "gestione_finanziaria",
        LivelloPermesso.VISUALIZZAZIONE,
    )
    can_manage_gestione_finanziaria = user_has_module_permission(
        user,
        "gestione_finanziaria",
        LivelloPermesso.GESTIONE,
    )
    can_view_gestione_amministrativa = user_has_module_permission(
        user,
        "gestione_amministrativa",
        LivelloPermesso.VISUALIZZAZIONE,
    )
    can_manage_gestione_amministrativa = user_has_module_permission(
        user,
        "gestione_amministrativa",
        LivelloPermesso.GESTIONE,
    )

    can_manage_current_module = True
    if current_module == "anagrafica":
        can_manage_current_module = can_manage_anagrafica
    elif current_module == "economia":
        can_manage_current_module = can_manage_economia
    elif current_module == "sistema":
        can_manage_current_module = can_manage_sistema
    elif current_module == "calendario":
        can_manage_current_module = can_manage_calendario
    elif current_module == "servizi_extra":
        can_manage_current_module = can_manage_servizi_extra
    elif current_module == "gestione_finanziaria":
        can_manage_current_module = can_manage_gestione_finanziaria
    elif current_module == "gestione_amministrativa":
        can_manage_current_module = can_manage_gestione_amministrativa

    servizi_extra_sidebar_items = []
    current_servizio_extra_id = None

    if can_view_servizi_extra:
        current_servizio_extra_id = get_current_servizio_extra_id(request)
        try:
            from servizi_extra.models import ServizioExtra

            servizi_extra_sidebar_items = list(
                ServizioExtra.objects.select_related("anno_scolastico").all()
            )
        except (OperationalError, ProgrammingError):
            servizi_extra_sidebar_items = []

    return {
        "user_permission_profile": profilo,
        "current_permission_module": current_module,
        "current_module_view_only": bool(current_module) and not can_manage_current_module,
        "can_view_anagrafica": can_view_anagrafica,
        "can_manage_anagrafica": can_manage_anagrafica,
        "can_view_economia": can_view_economia,
        "can_manage_economia": can_manage_economia,
        "can_view_sistema": can_view_sistema,
        "can_manage_sistema": can_manage_sistema,
        "can_view_calendario": can_view_calendario,
        "can_manage_calendario": can_manage_calendario,
        "can_view_servizi_extra": can_view_servizi_extra,
        "can_manage_servizi_extra": can_manage_servizi_extra,
        "can_view_gestione_finanziaria": can_view_gestione_finanziaria,
        "can_manage_gestione_finanziaria": can_manage_gestione_finanziaria,
        "can_view_gestione_amministrativa": can_view_gestione_amministrativa,
        "can_manage_gestione_amministrativa": can_manage_gestione_amministrativa,
        "servizi_extra_sidebar_items": servizi_extra_sidebar_items,
        "current_servizio_extra_id": current_servizio_extra_id,
        "can_view_operation_history": user_is_operational_admin(user),
        "can_access_database_backups": user_can_access_database_backups(user),
    }
