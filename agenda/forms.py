from django import forms
from django.utils import timezone
from datetime import timedelta

from .models import (
    Appointment,
    Client,
    Service,
    BarberShop,
    Cancellation,
    Product,
    ProductSale,
    WorkDayConfig,
)


class NovoAgendamentoForm(forms.ModelForm):
    inicio = forms.DateTimeField(
        label="Data e horário",
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "form-control"
            }
        )
    )

    class Meta:
        model = Appointment
        fields = ['cliente', 'servico', 'inicio']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'form-select'}),
            'servico': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        barbearia = kwargs.pop('barbearia', None)
        super().__init__(*args, **kwargs)

        if barbearia:
            self.fields['cliente'].queryset = Client.objects.filter(barbearia=barbearia)
            self.fields['servico'].queryset = Service.objects.filter(barbearia=barbearia, ativo=True)

        self.fields['cliente'].required = True
        self.fields['servico'].required = True

    def save(self, commit=True, barbearia: BarberShop = None):
        agendamento = super().save(commit=False)

        if not barbearia:
            raise ValueError("Barbearia é obrigatória para salvar o agendamento.")

        agendamento.barbearia = barbearia
        servico = agendamento.servico

        duracao = timedelta(minutes=servico.duracao_minutos or 30)
        agendamento.fim = agendamento.inicio + duracao

        agendamento.valor_no_momento = servico.preco
        agendamento.criado_via = 'manual'
        agendamento.status = 'confirmado'

        if commit:
            agendamento.save()
        return agendamento


class CancelamentoForm(forms.ModelForm):
    class Meta:
        model = Cancellation
        fields = ['motivo', 'observacao']
        widgets = {
            'motivo': forms.Select(attrs={'class': 'form-select'}),
            'observacao': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Opcional: motivo do cancelamento...'
            }),
        }


class RemarcarAgendamentoForm(forms.ModelForm):
    inicio = forms.DateTimeField(
        label="Nova data e horário",
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "form-control"
            }
        )
    )

    class Meta:
        model = Appointment
        fields = ['inicio']

    def save(self, commit=True):
        agendamento = super().save(commit=False)
        duracao = timedelta(minutes=agendamento.servico.duracao_minutos or 30)
        agendamento.fim = agendamento.inicio + duracao

        if commit:
            agendamento.save()
        return agendamento

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['nome', 'preco', 'duracao_minutos', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'preco': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'duracao_minutos': forms.NumberInput(attrs={'class': 'form-control'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['nome', 'preco', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'preco': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class WorkDayConfigForm(forms.ModelForm):
    class Meta:
        model = WorkDayConfig
        fields = ["dia_semana", "inicio", "fim", "ativo"]
        widgets = {
            "inicio": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "fim": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "dia_semana": forms.Select(attrs={"class": "form-select"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
# ==========================
# FORMULÁRIOS PÚBLICOS (CLIENTE)
# ==========================

class PublicEscolherServicoForm(forms.Form):
    servico = forms.ModelChoiceField(
        queryset=Service.objects.none(),
        label="Escolha o serviço",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    data = forms.DateField(
        label="Escolha o dia",
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control'
            }
        )
    )

    def __init__(self, *args, **kwargs):
        barbearia = kwargs.pop('barbearia', None)
        super().__init__(*args, **kwargs)

        if barbearia:
            self.fields['servico'].queryset = Service.objects.filter(
                barbearia=barbearia,
                ativo=True
            )


class PublicConfirmarDadosForm(forms.Form):
    nome = forms.CharField(
        label="Seu nome",
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    telefone = forms.CharField(
        label="WhatsApp (com DDD)",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

class ProductSaleForm(forms.ModelForm):
    class Meta:
        model = ProductSale
        fields = ['produto', 'quantidade', 'valor_unitario', 'observacao']
        widgets = {
            'produto': forms.Select(attrs={'class': 'form-select'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'valor_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
        }

    def __init__(self, *args, **kwargs):
        barbearia = kwargs.pop('barbearia', None)
        super().__init__(*args, **kwargs)
        if barbearia:
            self.fields['produto'].queryset = Product.objects.filter(
                barbearia=barbearia,
                ativo=True
            )

    def save(self, commit=True, barbearia=None):
        venda = super().save(commit=False)
        if not barbearia:
            raise ValueError("Barbearia é obrigatória para salvar a venda.")
        venda.barbearia = barbearia
        venda.valor_total = venda.quantidade * venda.valor_unitario
        if commit:
            venda.save()
        return venda