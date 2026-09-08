from django.db import migrations
from django.db.models import Q


def conserva_letture_notifiche_import(apps, schema_editor):
    Notifica = apps.get_model("gestione_finanziaria", "NotificaFinanziaria")
    Lettura = apps.get_model("gestione_finanziaria", "NotificaFinanziariaLettura")
    database = schema_editor.connection.alias
    notifiche = Notifica.objects.using(database).filter(
        Q(chiave_deduplica__startswith="fic-document-") | Q(chiave_deduplica__startswith="fic-documento-"),
        tipo="fattura_ricevuta", documento_id__isnull=False,
    )
    documenti = list(notifiche.order_by().values_list("documento_id", flat=True).distinct())
    for documento_id in documenti:
        chiave = f"fic-documento-{documento_id}"
        gruppo = list(notifiche.filter(documento_id=documento_id).order_by("id"))
        conservata = next((n for n in gruppo if n.chiave_deduplica == chiave), gruppo[0])
        for duplicata in gruppo:
            if duplicata.pk == conservata.pk:
                continue
            lettori = Lettura.objects.using(database).filter(notifica_id=conservata.pk).values("user_id")
            Lettura.objects.using(database).filter(notifica_id=duplicata.pk).exclude(user_id__in=lettori).update(notifica_id=conservata.pk)
            duplicata.delete(using=database)
        Notifica.objects.using(database).filter(pk=conservata.pk).update(chiave_deduplica=chiave)


class Migration(migrations.Migration):
    dependencies = [("gestione_finanziaria", "0013_documentofornitore_proforma_origine_and_more")]
    operations = [migrations.RunPython(conserva_letture_notifiche_import, migrations.RunPython.noop)]
