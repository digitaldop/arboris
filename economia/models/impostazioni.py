from django.db import models


class MetodoPagamento(models.Model):
    metodo_pagamento = models.CharField(max_length=100, unique=True)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_metodo_pagamento"
        ordering = ["metodo_pagamento"]
        verbose_name = "Metodo pagamento"
        verbose_name_plural = "Metodi pagamento"

    def __str__(self):
        return self.metodo_pagamento


class TipoMovimentoCredito(models.Model):
    tipo_movimento_credito = models.CharField(max_length=100, unique=True)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_tipo_movimento_credito"
        ordering = ["tipo_movimento_credito"]
        verbose_name = "Tipo movimento credito"
        verbose_name_plural = "Tipi movimento credito"

    def __str__(self):
        return self.tipo_movimento_credito

