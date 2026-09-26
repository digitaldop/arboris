from functools import wraps

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import redirect

from .models import (
    LivelloPermesso,
    MODULE_SETTINGS_CACHE_KEY,
    MODULES_ALWAYS_ENABLED,
    SistemaUtentePermessi,
    get_module_enabled_map,
)
from .permission_catalog import PERMISSION_PAGES, PAGES_BY_KEY, SHARED_PAGE_VIEWS, page_for_match


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
FAMILY_COMMUNICATIONS_VIEW_MODULE = "economia.views.comunicazioni"
EDIT_MODE_QUERY_VALUES = {"1", "true", "on", "yes", "si"}
# These POSTs only record the current user's reading progress, not business data.
READ_RECEIPT_VIEWS = {
    "segna_notifica_finanziaria_letta", "segna_tutte_notifiche_finanziarie_lette",
    "segna_log_operazione_letta", "segna_tutti_log_operazioni_letti",
}


def redirect_unauthenticated_user(request):
    return redirect_to_login(
        request.get_full_path(),
        login_url="login",
        redirect_field_name=REDIRECT_FIELD_NAME,
    )


def authenticated_user_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return redirect_unauthenticated_user(request)
        return view_func(request, *args, **kwargs)

    return wrapped


def get_user_permission_profile(user):
    if not user or not user.is_authenticated:
        return None

    if user.is_superuser:
        return None

    cached = getattr(user, "_arboris_permission_profile_cache", None)
    if cached is not None:
        return cached

    profilo, _ = SistemaUtentePermessi.objects.select_related("ruolo_permessi").get_or_create(user=user)
    user._arboris_permission_profile_cache = profilo
    return profilo


def user_has_module_permission(user, module_name, level=LivelloPermesso.VISUALIZZAZIONE):
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if not module_is_enabled(module_name):
        return False

    if user.is_superuser:
        return True

    profilo = get_user_permission_profile(user)
    if not profilo:
        return False

    if profilo.controllo_completo_effettivo:
        return True

    return profilo.has_module_permission(module_name, level=level)


def user_has_page_permission(user, page_key, level=LivelloPermesso.VISUALIZZAZIONE):
    page = PAGES_BY_KEY.get(page_key)
    if not page or not user or not user.is_authenticated or not user.is_active:
        return False
    if not module_is_enabled(page.module):
        return False
    if user.is_superuser:
        return True
    profile = get_user_permission_profile(user)
    if profile.ruolo_permessi_id:
        current = profile.ruolo_permessi.get_page_level(page_key)
    elif profile.controllo_completo_effettivo:
        current = LivelloPermesso.GESTIONE
    else:
        special = {
            "anagrafica_comunicazioni_famiglie": profile.accesso_comunicazioni_famiglie_effettivo,
            "sistema_backup_database": profile.accesso_backup_database_effettivo,
            "sistema_cronologia_operazioni": profile.amministratore_operativo_effettivo,
            "sistema_feedback_beta": profile.amministratore_operativo_effettivo,
        }
        current = (
            (LivelloPermesso.GESTIONE if special[page_key] else LivelloPermesso.NESSUNO)
            if page_key in special else profile.get_module_level(page.module)
        )
    return current == LivelloPermesso.GESTIONE or (
        level == LivelloPermesso.VISUALIZZAZIONE and current == LivelloPermesso.VISUALIZZAZIONE
    )


def user_has_any_module_page_permission(user, module_name, level=LivelloPermesso.VISUALIZZAZIONE):
    return any(user_has_page_permission(user, page.key, level) for page in PERMISSION_PAGES if page.module == module_name)


def request_has_permission(request, module_name, level=LivelloPermesso.VISUALIZZAZIONE):
    page = page_for_match(getattr(request, "resolver_match", None))
    if page:
        keys = (page.key, *SHARED_PAGE_VIEWS.get(request.resolver_match.url_name, ()))
        return any(user_has_page_permission(request.user, key, level) for key in keys)
    return user_has_module_permission(request.user, module_name, level)


def request_permission_level(request, minimum=LivelloPermesso.VISUALIZZAZIONE):
    editing = str(request.GET.get("edit") or "").strip().lower() in EDIT_MODE_QUERY_VALUES
    reading = getattr(getattr(request, "resolver_match", None), "url_name", None) in READ_RECEIPT_VIEWS
    if minimum == LivelloPermesso.GESTIONE or (request.method not in SAFE_METHODS and not reading) or editing:
        return LivelloPermesso.GESTIONE
    return LivelloPermesso.VISUALIZZAZIONE


def module_is_enabled(module_name):
    if not module_name or module_name in MODULES_ALWAYS_ENABLED:
        return True

    try:
        enabled_map = cache.get(MODULE_SETTINGS_CACHE_KEY)
        if enabled_map is None:
            enabled_map = get_module_enabled_map()
            cache.set(MODULE_SETTINGS_CACHE_KEY, enabled_map, 300)
    except (OperationalError, ProgrammingError):
        return True

    return enabled_map.get(module_name, True)


def user_is_operational_admin(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    profilo = get_user_permission_profile(user)
    if not profilo:
        return False

    return bool(
        profilo.controllo_completo_effettivo
        or profilo.amministratore_operativo_effettivo
    )


def user_can_access_database_backups(user):
    return user_has_page_permission(user, "sistema_backup_database")


def user_can_communicate_with_families(user):
    return user_has_page_permission(user, "anagrafica_comunicazioni_famiglie")


def family_communications_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return redirect_unauthenticated_user(request)
        if not user_has_page_permission(request.user, "anagrafica_comunicazioni_famiglie", request_permission_level(request)):
            messages.error(request, "Non hai l'abilitazione alle comunicazioni alle famiglie.")
            return redirect("home")
        return view_func(request, *args, **kwargs)

    return wrapped


def module_permission_required(module_name, level=LivelloPermesso.VISUALIZZAZIONE):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not getattr(request.user, "is_authenticated", False):
                return redirect_unauthenticated_user(request)

            if not module_is_enabled(module_name):
                messages.warning(request, "Questo modulo e temporaneamente disattivato nelle impostazioni generali.")
                return redirect("home")

            if not request_has_permission(request, module_name, level=request_permission_level(request, level)):
                messages.error(request, "Non hai i permessi necessari per accedere a questa sezione.")
                return redirect("home")

            return view_func(request, *args, **kwargs)

        wrapped.permission_module = module_name
        wrapped.permission_level = level
        return wrapped

    return decorator


def module_edit_permission_required(module_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            explicit_edit_mode = (
                request.method in SAFE_METHODS
                and str(request.GET.get("edit") or "").strip().lower() in EDIT_MODE_QUERY_VALUES
            )
            required_level = (
                LivelloPermesso.VISUALIZZAZIONE
                if request.method in SAFE_METHODS and not explicit_edit_mode
                else LivelloPermesso.GESTIONE
            )

            if not getattr(request.user, "is_authenticated", False):
                return redirect_unauthenticated_user(request)

            if not module_is_enabled(module_name):
                messages.warning(request, "Questo modulo e temporaneamente disattivato nelle impostazioni generali.")
                return redirect("home")

            if not request_has_permission(request, module_name, level=required_level):
                messages.error(request, "Non hai i permessi necessari per eseguire questa operazione.")
                return redirect("home")

            return view_func(request, *args, **kwargs)

        wrapped.permission_module = module_name
        wrapped.permission_level = LivelloPermesso.VISUALIZZAZIONE
        return wrapped

    return decorator


def operational_admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return redirect_unauthenticated_user(request)

        page = page_for_match(getattr(request, "resolver_match", None))
        permitted = (user_has_page_permission(request.user, page.key, request_permission_level(request))
                     if page else user_is_operational_admin(request.user))
        if not permitted:
            messages.error(request, "Questa sezione e riservata all'Amministratore.")
            return redirect("home")

        return view_func(request, *args, **kwargs)

    return wrapped


def database_backup_access_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return redirect_unauthenticated_user(request)

        if not user_has_page_permission(request.user, "sistema_backup_database", request_permission_level(request)):
            messages.error(request, "La sezione Backup Database e riservata ad amministratori e superuser.")
            return redirect("home")

        return view_func(request, *args, **kwargs)

    return wrapped
