from functools import wraps

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from .models import LivelloPermesso, RuoloUtente, SistemaUtentePermessi


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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

    profilo, _ = SistemaUtentePermessi.objects.get_or_create(user=user)
    return profilo


def user_has_module_permission(user, module_name, level=LivelloPermesso.VISUALIZZAZIONE):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    profilo = get_user_permission_profile(user)
    if not profilo:
        return False

    if profilo.controllo_completo:
        return True

    return profilo.has_module_permission(module_name, level=level)


def user_is_operational_admin(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    profilo = get_user_permission_profile(user)
    if not profilo:
        return False

    return bool(
        profilo.controllo_completo
        or profilo.ruolo == RuoloUtente.AMMINISTRATORE
    )


def module_permission_required(module_name, level=LivelloPermesso.VISUALIZZAZIONE):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not getattr(request.user, "is_authenticated", False):
                return redirect_unauthenticated_user(request)

            if not user_has_module_permission(request.user, module_name, level=level):
                messages.error(request, "Non hai i permessi necessari per accedere a questa sezione.")
                return redirect("home")

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def module_edit_permission_required(module_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            required_level = (
                LivelloPermesso.VISUALIZZAZIONE
                if request.method in SAFE_METHODS
                else LivelloPermesso.GESTIONE
            )

            if not getattr(request.user, "is_authenticated", False):
                return redirect_unauthenticated_user(request)

            if not user_has_module_permission(request.user, module_name, level=required_level):
                messages.error(request, "Non hai i permessi necessari per eseguire questa operazione.")
                return redirect("home")

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def operational_admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return redirect_unauthenticated_user(request)

        if not user_is_operational_admin(request.user):
            messages.error(request, "Questa sezione e riservata all'Amministratore.")
            return redirect("home")

        return view_func(request, *args, **kwargs)

    return wrapped
