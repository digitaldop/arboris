import gzip
import json
import os
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from gestione_finanziaria import background_scheduler
from sistema import backup_scheduler
from sistema.middleware import DatabaseBackupScheduleMiddleware
from sistema.static_storage import OptimizedStaticFilesStorage


class BackgroundLoadingTests(SimpleTestCase):
    def test_disabling_finance_scheduler_does_not_disable_automatic_backups(self):
        with patch.dict(os.environ, {"ARBORIS_BACKGROUND_SCHEDULER_ENABLED": "0"}, clear=True):
            with patch.object(background_scheduler.sys, "argv", ["gunicorn", "arboris.wsgi:application"]):
                self.assertFalse(background_scheduler.should_start_background_scheduler()[0])
                self.assertTrue(background_scheduler.should_start_background_scheduler(
                    enabled_env_var="ARBORIS_BACKGROUND_BACKUP_ENABLED",
                )[0])

    def test_backup_trigger_returns_while_backup_is_still_running_and_throttles(self):
        started = threading.Event()
        release = threading.Event()

        def slow_backup(user_id):
            started.set()
            release.wait(5)

        with patch.object(background_scheduler, "should_start_background_scheduler", return_value=(True, "test")):
            with patch.object(backup_scheduler, "_thread", None), patch.object(backup_scheduler, "_last_check", None):
                with patch.object(backup_scheduler, "_run_backup", side_effect=slow_backup):
                    try:
                        self.assertTrue(backup_scheduler.trigger_due_backup_check_async())
                        self.assertTrue(started.wait(2))
                        self.assertTrue(backup_scheduler._thread.is_alive())
                        self.assertFalse(backup_scheduler.trigger_due_backup_check_async())
                    finally:
                        release.set()
                        if backup_scheduler._thread:
                            backup_scheduler._thread.join(2)
                    self.assertFalse(backup_scheduler.trigger_due_backup_check_async())

    def test_backup_worker_closes_connections_on_failure(self):
        with patch.object(backup_scheduler, "maybe_run_scheduled_backup", side_effect=RuntimeError("failure")):
            with patch.object(backup_scheduler.connections, "close_all") as close:
                with self.assertLogs("sistema.backup_scheduler", level="ERROR"):
                    backup_scheduler._run_backup(None)
                close.assert_called_once()

    def test_backup_middleware_queues_only_eligible_responses(self):
        with patch("sistema.middleware.trigger_due_backup_check_async") as trigger:
            middleware = DatabaseBackupScheduleMiddleware(lambda request: HttpResponse("ok"))
            for method, path in (("post", "/"), ("get", "/static/test.css"), ("get", "/media/test"), ("get", "/admin/")):
                middleware(getattr(RequestFactory(), method)(path))
            trigger.assert_not_called()
            self.assertEqual(middleware(RequestFactory().get("/")).content, b"ok")
            trigger.assert_called_once()

    def test_finance_kick_does_not_spawn_a_thread_per_request(self):
        worker = Mock()
        worker.is_alive.return_value = False
        with patch.object(background_scheduler, "should_start_background_scheduler", return_value=(True, "test")):
            with patch.object(background_scheduler, "_kick_thread", None), patch.object(background_scheduler, "_last_kick_at", None):
                with patch.object(background_scheduler.threading, "Thread", return_value=worker) as factory:
                    with patch.object(background_scheduler.time, "monotonic", side_effect=[100, 101, 161]):
                        self.assertTrue(background_scheduler.trigger_due_sync_check_async())
                        self.assertFalse(background_scheduler.trigger_due_sync_check_async())
                        self.assertTrue(background_scheduler.trigger_due_sync_check_async())
                    self.assertEqual(factory.call_count, 2)


class StaticBuildPerformanceTests(SimpleTestCase):
    def test_minification_preserves_sources_hashes_urls_and_gzip(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as build_dir:
            source = FileSystemStorage(source_dir)
            original = '/*! License */\n/* Build comment to remove. */\n.box {\n    width: calc(100% - 20px);\n    content: "a  b";\n    background: url("../images/test.svg");\n}\n' * 12
            source.save("css/app.css", ContentFile(original.encode()))
            source.save("images/test.svg", ContentFile(b'<svg xmlns="http://www.w3.org/2000/svg"/>'))
            paths = {name: (source, name) for name in ("css/app.css", "images/test.svg")}
            with override_settings(STATIC_ROOT=build_dir, STATIC_URL="/static/"):
                storage = OptimizedStaticFilesStorage()
                for name in paths:
                    with source.open(name) as content_file:
                        storage.save(name, content_file)
                results = list(storage.post_process(paths))
                self.assertFalse([result for result in results if isinstance(result[2], Exception)])
                manifest = json.loads((Path(build_dir) / "staticfiles.json").read_text())
                hashed_css = manifest["paths"]["css/app.css"]
                css_path = Path(build_dir) / hashed_css
                content = css_path.read_text()
                self.assertLess(len(content), len(original))
                self.assertIn('calc(100% - 20px)', content)
                self.assertIn('"a  b"', content)
                self.assertIn('/*! License */', content)
                self.assertIn(manifest["paths"]["images/test.svg"].replace("images/", "../images/"), content)
                self.assertEqual(gzip.decompress(Path(str(css_path) + ".gz").read_bytes()), css_path.read_bytes())
                self.assertEqual((Path(source_dir) / "css/app.css").read_text(), original)
                self.assertEqual(storage.clean_name(storage.hashed_name("css/app.css", ContentFile(css_path.read_bytes()))), hashed_css)
