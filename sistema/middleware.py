from .audit import reset_current_audit_user, set_current_audit_user
from .audit_accessi import log_page_view
from .backup_scheduler import trigger_due_backup_check_async


class PagePermissionMiddleware:
    """Enforce page permissions for direct URLs, POSTs and auxiliary endpoints."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from django.contrib import messages
        from django.shortcuts import redirect
        from .permission_catalog import page_for_match
        from .permissions import (
            redirect_unauthenticated_user, request_permission_level, request_has_permission,
        )

        page = page_for_match(request.resolver_match)
        # Attribution is linked from the public login page as well as the sidebar.
        if not page or request.resolver_match.url_name == "crediti":
            return None
        if not request.user.is_authenticated:
            return redirect_unauthenticated_user(request)
        minimum = getattr(view_func, "permission_level", "view")
        # OAuth callbacks change saved credentials even though providers use GET.
        if request.resolver_match.url_name in {"callback_connessione_psd2", "callback_oauth_psd2"}:
            minimum = "manage"
        if not request_has_permission(request, page.module, request_permission_level(request, minimum)):
            messages.error(request, "Non hai i permessi necessari per accedere a questa pagina o eseguire questa operazione.")
            return redirect("home")
        return None


class AuditUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_audit_user(getattr(request, "user", None))
        try:
            response = self.get_response(request)
            log_page_view(request, response)
        finally:
            if token is not None:
                reset_current_audit_user(token)

        return response


class DatabaseBackupScheduleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method in {"GET", "HEAD", "OPTIONS"} and response.status_code < 500:
            path = request.path or ""
            if not path.startswith("/admin/") and not path.startswith("/media/") and not path.startswith("/static/"):
                trigger_due_backup_check_async(getattr(request, "user", None))

        return response
