from copy import deepcopy
from urllib.parse import urlsplit

from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.urls import Resolver404, resolve

from .models import (
    LivelloPermesso,
    Scuola,
    SidebarPersonalizzazione,
    SistemaImpostazioniGenerali,
    SistemaUtentePermessi,
    get_site_font_settings,
)
from .permissions import (
    get_user_permission_profile,
    user_can_access_database_backups,
    user_has_module_permission,
    user_is_operational_admin,
)
from .sidebar_menu import build_sidebar_menu_state, get_role_sidebar_menu_disabled_keys
from .terminology import get_educator_terminology, get_family_member_terminology, get_student_terminology


def permission_module_from_view(view_module, path=""):
    if view_module.startswith("anagrafica."):
        return "anagrafica"
    if view_module.startswith("osservazioni."):
        return "anagrafica"
    if view_module.startswith("famiglie_interessate."):
        return "famiglie_interessate"
    if view_module.startswith("economia."):
        return "economia"
    if view_module.startswith("fondo_accantonamento."):
        return "economia"
    if view_module.startswith("calendario."):
        return "calendario"
    if view_module.startswith("servizi_extra."):
        return "servizi_extra"
    if view_module.startswith("gestione_finanziaria."):
        return "gestione_finanziaria"
    if view_module.startswith("gestione_amministrativa."):
        return "gestione_amministrativa"
    if view_module.startswith("archivio_storico."):
        return "sistema"
    if view_module.startswith("scuola."):
        return "sistema"
    if view_module.startswith("sistema."):
        return "sistema"
    if path.startswith(("/scuola/calendario/", "/calendario/")):
        return "calendario"
    return ""


def get_current_permission_module(request):
    resolver_match = getattr(request, "resolver_match", None)
    if not resolver_match or not getattr(resolver_match, "func", None):
        return ""

    if getattr(resolver_match, "url_name", "") == "home":
        return ""

    view_module = getattr(resolver_match.func, "__module__", "")
    return permission_module_from_view(view_module, getattr(request, "path", ""))


def scuola_context(request):
    scuola = cache.get("sistema:scuola_header")
    if scuola is None:
        scuola = (
            Scuola.objects.select_related(
                "indirizzo_sede_legale__provincia",
                "indirizzo_sede_legale__regione",
                "indirizzo_sede_legale__citta__provincia",
                "indirizzo_operativo__provincia",
                "indirizzo_operativo__regione",
                "indirizzo_operativo__citta__provincia",
            )
            .prefetch_related("telefoni", "email")
            .first()
        )
        cache.set("sistema:scuola_header", scuola, 300)

    return {
        "scuola_header": scuola,
    }


def general_settings_context(request):
    try:
        general_settings = cache.get("sistema:general_settings")
        if general_settings is None:
            general_settings = SistemaImpostazioniGenerali.objects.first()
            cache.set("sistema:general_settings", general_settings, 300)
    except (OperationalError, ProgrammingError):
        general_settings = None

    interfaccia_colorata_attiva = bool(
        getattr(general_settings, "interfaccia_colorata_attiva", True)
    )
    interfaccia_professionale_attiva = bool(
        getattr(general_settings, "interfaccia_professionale_attiva", False)
    )
    stile_streamline_attivo = bool(
        getattr(general_settings, "stile_streamline_attivo", False)
    )
    stile_iconscout_3d_attivo = bool(
        getattr(general_settings, "stile_iconscout_3d_attivo", False)
    )

    return {
        "general_settings": general_settings,
        "interfaccia_colorata_attiva": interfaccia_colorata_attiva,
        "interfaccia_professionale_attiva": interfaccia_professionale_attiva,
        "stile_streamline_attivo": stile_streamline_attivo,
        "stile_iconscout_3d_attivo": stile_iconscout_3d_attivo,
        "gestione_dipendenti_dettagliata_attiva": bool(
            getattr(general_settings, "gestione_dipendenti_dettagliata_attiva", False)
        ),
        "site_fonts": get_site_font_settings(general_settings),
        "student_terminology": get_student_terminology(
            getattr(general_settings, "terminologia_studente", None)
        ),
        "family_member_terminology": get_family_member_terminology(
            getattr(general_settings, "terminologia_familiare", None)
        ),
        "educator_terminology": get_educator_terminology(
            getattr(general_settings, "terminologia_educatore", None)
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


def sidebar_user_is_canonical_admin(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    try:
        profilo = user.profilo_permessi
    except (AttributeError, SistemaUtentePermessi.DoesNotExist):
        return False
    return bool(
        profilo.controllo_completo_effettivo
        or profilo.amministratore_operativo_effettivo
    )


def user_can_access_sidebar_url(user, url):
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme or parsed.netloc:
        return True
    if not parsed.path or not parsed.path.startswith("/"):
        return True

    try:
        resolver_match = resolve(parsed.path)
    except Resolver404:
        return True

    if getattr(resolver_match, "url_name", "") == "home":
        return True

    module_name = permission_module_from_view(
        getattr(resolver_match.func, "__module__", ""),
        parsed.path,
    )
    if not module_name:
        return True
    return user_has_module_permission(user, module_name, LivelloPermesso.VISUALIZZAZIONE)


def filter_sidebar_config_for_user(config, user):
    filtered_config = deepcopy(config) if isinstance(config, dict) else {}
    custom_sections = []
    for section in filtered_config.get("custom_sections", []) or []:
        if not isinstance(section, dict):
            continue
        links = [
            link
            for link in section.get("links", []) or []
            if isinstance(link, dict) and user_can_access_sidebar_url(user, link.get("url"))
        ]
        if links:
            filtered_section = deepcopy(section)
            filtered_section["links"] = links
            custom_sections.append(filtered_section)
    if custom_sections:
        filtered_config["custom_sections"] = custom_sections
    else:
        filtered_config.pop("custom_sections", None)
    return filtered_config


def get_effective_sidebar_personalizzazione_config(user):
    if not user or not getattr(user, "is_authenticated", False):
        return {}

    personalizzazione = SidebarPersonalizzazione.objects.filter(user=user).first()
    if sidebar_user_is_canonical_admin(user):
        if personalizzazione:
            return filter_sidebar_config_for_user(personalizzazione.config, user)
        return {}

    for admin_personalizzazione in SidebarPersonalizzazione.objects.select_related(
        "user",
        "user__profilo_permessi",
        "user__profilo_permessi__ruolo_permessi",
    ).order_by("-user__is_superuser", "user_id"):
        if sidebar_user_is_canonical_admin(admin_personalizzazione.user):
            return filter_sidebar_config_for_user(admin_personalizzazione.config, user)

    if personalizzazione:
        return filter_sidebar_config_for_user(personalizzazione.config, user)

    return {}


def sistema_permissions_context(request):
    user = getattr(request, "user", None)
    profilo = get_user_permission_profile(user)
    current_module = get_current_permission_module(request)
    can_view_anagrafica = user_has_module_permission(user, "anagrafica", LivelloPermesso.VISUALIZZAZIONE)
    can_manage_anagrafica = user_has_module_permission(user, "anagrafica", LivelloPermesso.GESTIONE)
    can_view_famiglie_interessate = user_has_module_permission(
        user,
        "famiglie_interessate",
        LivelloPermesso.VISUALIZZAZIONE,
    )
    can_manage_famiglie_interessate = user_has_module_permission(
        user,
        "famiglie_interessate",
        LivelloPermesso.GESTIONE,
    )
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
    elif current_module == "famiglie_interessate":
        can_manage_current_module = can_manage_famiglie_interessate
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

    can_view_system_tables = user_is_operational_admin(user)
    role_theme = profilo.role_theme_variables if profilo else None
    can_access_database_backups = user_can_access_database_backups(user)
    gestione_dipendenti_dettagliata_attiva = False
    try:
        general_settings = cache.get("sistema:general_settings")
        if general_settings is None:
            general_settings = SistemaImpostazioniGenerali.objects.first()
        gestione_dipendenti_dettagliata_attiva = bool(
            getattr(general_settings, "gestione_dipendenti_dettagliata_attiva", False)
        )
    except (OperationalError, ProgrammingError):
        gestione_dipendenti_dettagliata_attiva = False

    sidebar_menu_disabled_keys = []
    ruolo_permessi = getattr(profilo, "ruolo_permessi", None) if profilo else None
    if ruolo_permessi and ruolo_permessi.attivo:
        sidebar_menu_disabled_keys = get_role_sidebar_menu_disabled_keys(ruolo_permessi)

    sidebar_menu_state = build_sidebar_menu_state(
        sidebar_menu_disabled_keys,
        {
            "can_view_anagrafica": can_view_anagrafica,
            "can_manage_anagrafica": can_manage_anagrafica,
            "can_view_famiglie_interessate": can_view_famiglie_interessate,
            "can_manage_famiglie_interessate": can_manage_famiglie_interessate,
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
            "can_view_operation_history": can_view_system_tables,
            "can_view_system_tables": can_view_system_tables,
            "can_access_database_backups": can_access_database_backups,
            "gestione_dipendenti_dettagliata_attiva": gestione_dipendenti_dettagliata_attiva,
        },
    )
    notifiche_finanziarie_non_lette = 0
    notifiche_finanziarie_recenti = []
    sidebar_personalizzazione_config = {}

    if can_view_gestione_finanziaria and getattr(user, "is_authenticated", False):
        try:
            from gestione_finanziaria.models import NotificaFinanziaria

            notifiche_qs = NotificaFinanziaria.objects.select_related("documento").exclude(letture__user=user)
            if not can_manage_gestione_finanziaria:
                notifiche_qs = notifiche_qs.filter(richiede_gestione=False)
            notifiche_finanziarie_non_lette = notifiche_qs.count()
            notifiche_finanziarie_recenti = list(notifiche_qs.order_by("-data_creazione", "-id")[:5])
        except (OperationalError, ProgrammingError):
            notifiche_finanziarie_non_lette = 0
            notifiche_finanziarie_recenti = []

    return {
        "user_permission_profile": profilo,
        "role_theme": role_theme,
        "current_permission_module": current_module,
        "can_manage_current_module": can_manage_current_module,
        "current_module_view_only": bool(current_module) and not can_manage_current_module,
        "can_view_anagrafica": can_view_anagrafica,
        "can_manage_anagrafica": can_manage_anagrafica,
        "can_view_famiglie_interessate": can_view_famiglie_interessate,
        "can_manage_famiglie_interessate": can_manage_famiglie_interessate,
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
        "can_view_operation_history": can_view_system_tables,
        "can_view_system_tables": can_view_system_tables,
        "can_access_database_backups": can_access_database_backups,
        "notifiche_finanziarie_non_lette": notifiche_finanziarie_non_lette,
        "notifiche_finanziarie_recenti": notifiche_finanziarie_recenti,
        "sidebar_personalizzazione_config": sidebar_personalizzazione_config,
        "sidebar_menu_items": sidebar_menu_state["items"],
        "sidebar_menu_groups": sidebar_menu_state["groups"],
        "sidebar_menu_disabled_keys": sidebar_menu_disabled_keys,
    }


def arboris_popup_manifest_context(request):
    from sistema.popup_manifest import build_popup_manifest

    return {"arboris_popup_manifest": build_popup_manifest()}
