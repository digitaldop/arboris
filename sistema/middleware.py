from .audit import reset_current_audit_user, set_current_audit_user
from .database_backups import maybe_run_scheduled_backup


class AuditUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_audit_user(getattr(request, "user", None))
        try:
            response = self.get_response(request)
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
                maybe_run_scheduled_backup(getattr(request, "user", None))

        return response
