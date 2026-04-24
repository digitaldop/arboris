from django.db import migrations, models
import django.db.models.deletion
import re


PATTERN = re.compile(r"^(?P<nome>.+?) \((?P<sigla>[A-Z]{2})\)$")


def find_citta(Citta, raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None

    matched = PATTERN.match(value)
    if matched:
        citta = Citta.objects.filter(
            nome=matched.group("nome"),
            provincia__sigla=matched.group("sigla"),
        ).first()
        if citta:
            return citta

    return Citta.objects.filter(nome=value).order_by("provincia__sigla").first()


def migrate_luoghi_nascita(apps, schema_editor):
    Citta = apps.get_model("anagrafica", "Citta")
    Studente = apps.get_model("anagrafica", "Studente")
    Familiare = apps.get_model("anagrafica", "Familiare")

    for studente in Studente.objects.exclude(luogo_nascita_testo="").iterator():
        citta = find_citta(Citta, studente.luogo_nascita_testo)
        if citta:
            studente.luogo_nascita_id = citta.pk
            studente.save(update_fields=["luogo_nascita"])

    for familiare in Familiare.objects.exclude(luogo_nascita_testo="").iterator():
        citta = find_citta(Citta, familiare.luogo_nascita_testo)
        if citta:
            familiare.luogo_nascita_id = citta.pk
            familiare.save(update_fields=["luogo_nascita"])


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0006_auto_ordini"),
    ]

    operations = [
        migrations.RenameField(
            model_name="familiare",
            old_name="luogo_nascita",
            new_name="luogo_nascita_testo",
        ),
        migrations.RenameField(
            model_name="studente",
            old_name="luogo_nascita",
            new_name="luogo_nascita_testo",
        ),
        migrations.AddField(
            model_name="familiare",
            name="luogo_nascita",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="familiari_nati",
                to="anagrafica.citta",
            ),
        ),
        migrations.AddField(
            model_name="studente",
            name="luogo_nascita",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="studenti_nati",
                to="anagrafica.citta",
            ),
        ),
        migrations.RunPython(migrate_luoghi_nascita, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="familiare",
            name="luogo_nascita_testo",
        ),
        migrations.RemoveField(
            model_name="studente",
            name="luogo_nascita_testo",
        ),
    ]
