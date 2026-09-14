from django.db import migrations


def queue_tuition_movements(apps, schema_editor):
    alias = schema_editor.connection.alias
    Movement = apps.get_model("gestione_finanziaria", "MovimentoFinanziario")
    Job = apps.get_model("gestione_finanziaria", "RichiestaAnalisiRiconciliazione")
    batch = []
    movements = Movement.objects.using(alias).filter(
        canale="banca", sostenuta_da_terzi=False, valuta__iexact="EUR", importo__gt=0,
    ).exclude(stato_riconciliazione="ignorato")
    for pk in movements.values_list("pk", flat=True).iterator(chunk_size=500):
        batch.append(Job(tipo="movimento", oggetto_id=pk))
        if len(batch) == 500:
            Job.objects.using(alias).bulk_create(batch, ignore_conflicts=True)
            batch = []
    Job.objects.using(alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("gestione_finanziaria", "0016_proposte_riconciliazione")]
    operations = [migrations.RunPython(queue_tuition_movements, migrations.RunPython.noop)]
