"""Minify CSS at build time, before WhiteNoise hashing and compression."""

from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from rcssmin import cssmin
from whitenoise.storage import CompressedManifestStaticFilesStorage


class OptimizedStaticFilesStorage(CompressedManifestStaticFilesStorage):
    def post_process(self, paths, dry_run=False, **options):
        if not dry_run:
            paths = paths.copy()
            minified = InMemoryStorage()
            for name, (source_storage, source_path) in paths.items():
                if not name.lower().endswith(".css"):
                    continue
                with source_storage.open(source_path) as source:
                    content = cssmin(source.read().decode("utf-8"), keep_bang_comments=True)
                minified.save(name, ContentFile(content.encode("utf-8")))
                paths[name] = (minified, name)
        yield from super().post_process(paths, dry_run=dry_run, **options)
