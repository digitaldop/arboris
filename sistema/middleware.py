from .audit import reset_current_audit_user, set_current_audit_user
from .audit_accessi import log_page_view
from .backup_scheduler import trigger_due_backup_check_async


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
