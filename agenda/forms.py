import re
from django import forms
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.contrib.auth.models import User
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError

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
    cliente_nome = forms.CharField(
        label="Cliente",
        required=True,
        widget=forms.TextInput(attrs={
            "class": "form-control ap-input",
            "placeholder": "Digite o nome do cliente",
            "autocomplete": "off",
        })
    )

    class Meta:
        model = Appointment
        fields = ["cliente_nome", "servico", "inicio", "status"]
        widgets = {
            "servico": forms.Select(attrs={"class": "form-select ap-input"}),
            "status": forms.Select(attrs={"class": "form-select ap-input"}),
            "inicio": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "form-control ap-input"
            }),
        }

    def __init__(self, *args, **kwargs):
        self._barbearia = kwargs.pop("barbearia", None)
        super().__init__(*args, **kwargs)

        # Filtra serviços da barbearia
        if self._barbearia:
            self.fields["servico"].queryset = Service.objects.filter(
                barbearia=self._barbearia, ativo=True
            ).order_by("nome")

        # Formato aceito pelo datetime-local
        self.fields["inicio"].input_formats = ["%Y-%m-%dT%H:%M"]

        # Status default
        if not self.initial.get("status"):
            self.initial["status"] = "confirmado"

        # Se está editando e já tem cliente, preenche o cliente_nome
        if self.instance and getattr(self.instance, "cliente_id", None) and not self.initial.get("cliente_nome"):
            self.initial["cliente_nome"] = self.instance.cliente.nome

    def save(self, barbearia=None, commit=True):
        barbearia = barbearia or self._barbearia
        obj = super().save(commit=False)

        if not barbearia:
            raise ValueError("Barbearia não informada no form.save()")

        obj.barbearia = barbearia

        # Resolve/cria cliente pelo nome digitado
        nome = (self.cleaned_data.get("cliente_nome") or "").strip()
        if not nome:
            raise forms.ValidationError("Informe o nome do cliente.")

        cliente = Client.objects.filter(barbearia=barbearia, nome__iexact=nome).first()
        if not cliente:
            cliente = Client.objects.create(barbearia=barbearia, nome=nome)

        obj.cliente = cliente

        # Calcula fim automático (se seu model tiver campo fim)
        if getattr(obj, "fim", None) is not None:
            dur = getattr(obj.servico, "duracao_minutos", 30) or 30
            if obj.inicio:
                obj.fim = obj.inicio + timedelta(minutes=dur)

        if commit:
            obj.save()

        return obj

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
    servico = forms.ModelChoiceField(queryset=None, empty_label="Selecione…")
    data = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, barbearia=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["servico"].queryset = barbearia.servicos.filter(ativo=True)

        self.fields["servico"].widget.attrs.update({
            "class": "form-select ap-input"
        })
        self.fields["data"].widget.attrs.update({
            "class": "form-control ap-input"
        })

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

from decimal import Decimal, InvalidOperation  # <- GARANTE ISSO
from django import forms
from django.core.exceptions import ValidationError

class ProductSaleForm(forms.ModelForm):
    produto = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        required=False,
        empty_label="Outro / não cadastrado",
        label="Produto",
    )

    # ✅ OVERRIDE AQUI: evita o Django tentar converter antes do seu clean
    valor_unitario = forms.CharField(
        required=False,
        label="Valor unitário (R$)",
    )

    class Meta:
        model = ProductSale
        fields = ["produto", "produto_nome", "quantidade", "valor_unitario", "observacao"]

    def __init__(self, *args, **kwargs):
        self.barbearia = kwargs.pop("barbearia", None)
        super().__init__(*args, **kwargs)

        if self.barbearia:
            self.fields["produto"].queryset = Product.objects.filter(
                barbearia=self.barbearia, ativo=True
            ).order_by("nome")

        self.fields["quantidade"].widget.attrs.update({"inputmode": "numeric"})
        self.fields["valor_unitario"].widget.attrs.update({
            "inputmode": "decimal",
            "placeholder": "0,00"
        })

    def clean_produto_nome(self):
        nome = (self.cleaned_data.get("produto_nome") or "").strip()
        produto = self.cleaned_data.get("produto")

        # se não escolheu produto cadastrado, exige nome manual
        if not produto and not nome:
            raise ValidationError("Informe o nome do produto (manual) ou selecione um cadastrado.")
        return nome

    def _parse_decimal_ptbr(self, raw, field_label="valor"):
        """
        Aceita: 10,00 | 10.00 | 10 | "R$ 10,00"
        """
        if raw in (None, ""):
            return None

        if isinstance(raw, (Decimal, int, float)):
            try:
                return Decimal(str(raw))
            except Exception:
                raise ValidationError(f"{field_label.capitalize()} inválido.")

        s = str(raw).strip()

        # remove "R$" e espaços
        s = s.replace("R$", "").replace(" ", "")

        # se vier 1.234,56 -> vira 1234.56
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            # se vier 10,00 -> vira 10.00
            s = s.replace(",", ".")

        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            raise ValidationError(f"{field_label.capitalize()} inválido. Ex: 10,00")

    def clean_quantidade(self):
        q = self.cleaned_data.get("quantidade")
        # se por algum motivo chegar como string "1"
        try:
            q_int = int(q)
        except Exception:
            raise ValidationError("Informe um número válido para quantidade.")
        if q_int <= 0:
            raise ValidationError("A quantidade deve ser maior que zero.")
        return q_int

    def clean_valor_unitario(self):
        produto = self.cleaned_data.get("produto")
        raw = self.cleaned_data.get("valor_unitario")

        # Se escolheu produto cadastrado e não digitou valor unitário,
        # deixa o model puxar do cadastro no save()
        if produto and (raw in (None, "")):
            return None

        valor = self._parse_decimal_ptbr(raw, "valor unitário")
        if valor is not None and valor < 0:
            raise ValidationError("O valor unitário não pode ser negativo.")
        return valor

    def save(self, commit=True, barbearia=None):
        obj = super().save(commit=False)
        if barbearia is not None:
            obj.barbearia = barbearia
        if commit:
            obj.save()
        return obj

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import BarberShop

User = get_user_model()


class SignupForm(forms.Form):
    username = forms.CharField(max_length=150, required=True, label="Usuário (username)")
    email = forms.EmailField(required=True, label="E-mail")
    telefone = forms.CharField(max_length=20, required=True, label="Telefone (WhatsApp)")

    nome_estabelecimento = forms.CharField(max_length=100, required=True, label="Nome do estabelecimento")
    tipo = forms.ChoiceField(choices=BarberShop.TIPO_CHOICES, required=True, label="Tipo")

    slug = forms.SlugField(max_length=60, required=True, label="Slug (link público)")

    password1 = forms.CharField(widget=forms.PasswordInput, required=True, label="Senha")
    password2 = forms.CharField(widget=forms.PasswordInput, required=True, label="Confirmar senha")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # classes bootstrap
        for name, f in self.fields.items():
            f.widget.attrs.update({"class": "form-control"})

        self.fields["tipo"].widget.attrs.update({"class": "form-select"})

        # anti-autofill / UX
        self.fields["password1"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["password2"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "placeholder": "ex: marquinhos"})
        self.fields["email"].widget.attrs.update({"autocomplete": "email", "placeholder": "ex: marcos@email.com"})
        self.fields["telefone"].widget.attrs.update({"inputmode": "tel", "placeholder": "ex: 19999999999"})
        self.fields["slug"].widget.attrs.update({"placeholder": "ex: marquinhos-barber"})

    def clean_username(self):
        u = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username__iexact=u).exists():
            raise ValidationError("Esse usuário já existe.")
        return u

    def clean_email(self):
        e = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=e).exists():
            raise ValidationError("Esse e-mail já está em uso.")
        return e

    def clean_slug(self):
        raw = (self.cleaned_data.get("slug") or "").strip()
        s = slugify(raw)
        if not s:
            raise ValidationError("Slug inválido.")
        if BarberShop.objects.filter(slug__iexact=s).exists():
            raise ValidationError("Esse slug já existe. Tenta outro (ex: agenda-maria).")
        return s

    def clean(self):
        data = super().clean()
        p1 = data.get("password1")
        p2 = data.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "As senhas não conferem.")

        if p1:
            validate_password(p1)

        return data

    def save(self):
        """Cria User + BarberShop e retorna (user, shop)."""
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
        )

        shop = BarberShop.objects.create(
            nome=self.cleaned_data["nome_estabelecimento"],
            tipo=self.cleaned_data["tipo"],
            slug=self.cleaned_data["slug"],
            telefone=self.cleaned_data["telefone"],
            dono=user,
        )

        return user, shop

class SignupEstabelecimentoForm(forms.Form):
    nome_estabelecimento = forms.CharField(max_length=100)
    tipo = forms.ChoiceField(choices=BarberShop.TIPO_CHOICES)
    telefone = forms.CharField(max_length=20, required=False)

    def clean_telefone(self):
        tel = (self.cleaned_data.get("telefone") or "").strip()
        if not tel:
            return ""
        digits = re.sub(r"\D+", "", tel)
        if len(digits) > 11 and digits.startswith("55"):
            digits = digits[2:]
        return digits

    slug = forms.SlugField(help_text="Vai virar seu link: /agendar/SEU-SLUG/")

    email = forms.EmailField()
    senha = forms.CharField(widget=forms.PasswordInput)
    senha2 = forms.CharField(widget=forms.PasswordInput, label="Confirmar senha")

    def clean_slug(self):
        slug = slugify(self.cleaned_data["slug"])
        if BarberShop.objects.filter(slug=slug).exists():
            raise ValidationError("Esse slug já existe. Tenta outro (ex: agenda-maria).")
        return slug

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("Esse email já está em uso. Tenta fazer login.")
        return email

    def clean(self):
        cleaned = super().clean()
        s1 = cleaned.get("senha")
        s2 = cleaned.get("senha2")
        if s1 and s2 and s1 != s2:
            self.add_error("senha2", "As senhas não batem.")
        if s1:
            validate_password(s1)
        return cleaned

    def save(self):
        email = self.cleaned_data["email"].lower().strip()
        senha = self.cleaned_data["senha"]

        user = User.objects.create_user(
            username=email,   # se você usa username padrão
            email=email,
            password=senha
        )

        estabelecimento = BarberShop.objects.create(
            nome=self.cleaned_data["nome_estabelecimento"],
            tipo=self.cleaned_data["tipo"],
            telefone=self.cleaned_data.get("telefone") or "",
            slug=self.cleaned_data["slug"],
            dono=user,
        )
        return user, estabelecimento
def save(self, barbearia, commit=True):
    nome = self.cleaned_data['cliente_nome'].strip()

    cliente, _ = Client.objects.get_or_create(
        barbearia=barbearia,
        nome__iexact=nome,
        defaults={'nome': nome}
    )

    agendamento = super().save(commit=False)
    agendamento.cliente = cliente
    agendamento.barbearia = barbearia

    if commit:
        agendamento.save()

    return agendamento


class RecurringBlockForm(forms.Form):
    """Cria bloqueios recorrentes com múltiplos dias (1 registro por dia)."""

    KIND_CHOICES = (("fixo", "Cliente fixo"), ("pausa", "Pausa"))
    DAYS = (
        (0, "Seg"), (1, "Ter"), (2, "Qua"), (3, "Qui"), (4, "Sex"), (5, "Sáb"), (6, "Dom")
    )

    kind = forms.ChoiceField(choices=KIND_CHOICES, initial="fixo")
    titulo = forms.CharField(max_length=80)
    dias = forms.MultipleChoiceField(choices=DAYS, widget=forms.CheckboxSelectMultiple)
    inicio = forms.TimeField()
    fim = forms.TimeField()
    servico = forms.ModelChoiceField(queryset=Service.objects.all(), required=False)
    duracao_minutos = forms.IntegerField(required=False, min_value=1)
    ativo = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # --- Visual premium (Bootstrap) ---
        self.fields["kind"].widget.attrs.update({"class": "form-select rounded-pill"})
        self.fields["titulo"].widget.attrs.update({
            "class": "form-control rounded-pill",
            "placeholder": "Ex.: João (pacote) ou Almoço",
        })

        # Dias: vamos renderizar manualmente no template (botões)
        self.fields["dias"].widget.attrs.update({"class": "btn-check"})

        # Horários
        time_attrs = {"class": "form-control rounded-pill", "type": "time"}
        self.fields["inicio"].widget = forms.TimeInput(attrs=time_attrs)
        self.fields["fim"].widget = forms.TimeInput(attrs=time_attrs)

        # Serviço (opcional)
        self.fields["servico"].widget.attrs.update({"class": "form-select rounded-pill"})
        self.fields["duracao_minutos"].widget.attrs.update({
            "class": "form-control rounded-pill",
            "placeholder": "Ex.: 30",
        })

    def clean(self):
        data = super().clean()
        ini = data.get("inicio")
        fim = data.get("fim")
        if ini and fim and fim <= ini:
            raise forms.ValidationError("O horário de fim precisa ser depois do início.")
        return data

# ==========================
# PORTAL DO CLIENTE (Login + Painel)
# ==========================

class PublicClienteLoginForm(forms.Form):
    nome = forms.CharField(label="Seu nome", max_length=120)
    telefone = forms.CharField(label="Seu telefone", max_length=30)

    def clean_telefone(self):
        tel = (self.cleaned_data.get("telefone") or "").strip()

        # mantém só dígitos
        digits = "".join(ch for ch in tel if ch.isdigit())

        if len(digits) < 8:
            raise forms.ValidationError("Telefone inválido.")

        if len(digits) > 11 and digits[:2] == "55":
            digits = digits[2:]

        return digits


class PublicClienteReagendarForm(forms.Form):
    """Reagendamento simples no portal do cliente (data + hora)."""

    data = forms.DateField(
        label="Nova data",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    hora = forms.TimeField(
        label="Novo horário",
        widget=forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
    )
