from django import forms

from economia.models import MetodoPagamento, TipoMovimentoCredito


class MetodoPagamentoForm(forms.ModelForm):
    class Meta:
        model = MetodoPagamento
        fields = ["metodo_pagamento", "attivo", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }


class TipoMovimentoCreditoForm(forms.ModelForm):
    class Meta:
        model = TipoMovimentoCredito
        fields = ["tipo_movimento_credito", "attivo", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }

