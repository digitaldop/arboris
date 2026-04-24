import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create admin user if missing"

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write("Missing superuser env vars, skipping.")
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email or "", "is_staff": True, "is_superuser": True},
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write("Superuser created.")
        else:
            self.stdout.write("Superuser already exists.")