from django.db import models



# util: padroniza telefone
def _digits_only(value):
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

User = get_user_model()


class BarberShop(models.Model):
    TIPO_CHOICES = [
        ('barbearia', 'Barbearia'),
        ('salao', 'Salão / Cabeleireiro'),
        ('manicure', 'Manicure'),
        ('sobrancelha', 'Sobrancelha'),
        ('maquiagem', 'Maquiagem'),
        ('outro', 'Outro'),
    ]
    nome = models.CharField(max_length=100)
    dono = models.ForeignKey(User, on_delete=models.CASCADE, related_name='estabelecimentos')
    telefone = models.CharField(max_length=20, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    slug = models.SlugField(unique=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='outro')

    def __str__(self):
        return self.nome
class Service(models.Model):
    """
    Serviços oferecidos: corte, barba, sobrancelha, luzes etc.
    """
    barbearia = models.ForeignKey(
        BarberShop,
        on_delete=models.CASCADE,
        related_name='servicos'
    )
    nome = models.CharField(max_length=100)
    duracao_minutos = models.PositiveIntegerField(default=30)
    preco = models.DecimalField(max_digits=8, decimal_places=2)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.nome} ({self.barbearia.nome})'

class Product(models.Model):
    barbearia = models.ForeignKey(
        BarberShop,
        on_delete=models.CASCADE,
        related_name='produtos'
    )
    nome = models.CharField(max_length=120)
    preco = models.DecimalField(max_digits=8, decimal_places=2)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"

    def __str__(self):
        return self.nome

class ProductSale(models.Model):
    barbearia = models.ForeignKey('BarberShop', on_delete=models.CASCADE, related_name='vendas_produtos')

    produto = models.ForeignKey(
        'Product',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='vendas'
    )

    # quando não existir no cadastro:
    produto_nome = models.CharField(max_length=120, blank=True, default="")

    quantidade = models.PositiveIntegerField(default=1)

    valor_unitario = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    data_hora = models.DateTimeField(default=timezone.now)
    observacao = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):
        # se tem produto e não veio valor_unitario, puxa do produto
        if self.produto_id and (self.valor_unitario is None or self.valor_unitario == ''):
            self.valor_unitario = self.produto.preco

        # calcula total sempre
        if self.valor_unitario is not None:
            self.valor_total = (self.quantidade or 1) * self.valor_unitario

        super().save(*args, **kwargs)

    def _str_(self):
        nome = self.produto.nome if self.produto_id else (self.produto_nome or "Produto")
        return f"{self.quantidade}x {nome} ({self.data_hora:%d/%m})"


class Client(models.Model):
    """
    Clientes da barbearia.
    """
    barbearia = models.ForeignKey(
        BarberShop,
        on_delete=models.CASCADE,
        related_name='clientes'
    )
    nome = models.CharField(max_length=120)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    bloqueado_online = models.BooleanField(
        default=False,
        help_text='Se verdadeiro, cliente não consegue marcar sozinho pelo link.'
    )


    def save(self, *args, **kwargs):
        # salva telefone sempre sem máscara (só dígitos)
        if self.telefone:
            self.telefone = _digits_only(self.telefone)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class WorkDayConfig(models.Model):
    """
    Blocos de horário por dia da semana (permite vários por dia: ex. sex 07-10 e 15-18).
    """
    DIAS_SEMANA = [
        (0, 'Segunda'),
        (1, 'Terça'),
        (2, 'Quarta'),
        (3, 'Quinta'),
        (4, 'Sexta'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    barbearia = models.ForeignKey(
        'BarberShop',
        on_delete=models.CASCADE,
        related_name='config_dias'
    )
    dia_semana = models.PositiveSmallIntegerField(choices=DIAS_SEMANA)
    inicio = models.TimeField()
    fim = models.TimeField()
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['dia_semana', 'inicio']

    def clean(self):
        # ✅ evita o erro "WorkDayConfig has no barbearia"
        if not self.barbearia_id:
            return

        if self.fim <= self.inicio:
            raise ValidationError("O horário de fim deve ser maior que o horário de início.")

        # evita blocos sobrepostos no mesmo dia
        qs = WorkDayConfig.objects.filter(
            barbearia_id=self.barbearia_id,
            dia_semana=self.dia_semana,
            ativo=True,
        ).exclude(pk=self.pk)

        # sobreposição: inicio < outro.fim e fim > outro.inicio
        conflito = qs.filter(inicio__lt=self.fim, fim__gt=self.inicio).exists()
        if conflito:
            raise ValidationError("Esse bloco sobrepõe outro bloco já cadastrado para esse dia.")

    def __str__(self):
        return f'{self.barbearia.nome} - {self.get_dia_semana_display()} {self.inicio}-{self.fim}'

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('aguardando', 'Aguardando confirmação'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
    ]

    ORIGEM_CHOICES = [
        ('cliente_link', 'Cliente via link'),
        ('whatsapp', 'WhatsApp'),
        ('manual', 'Manual'),
    ]

    barbearia = models.ForeignKey('BarberShop', on_delete=models.CASCADE, related_name='agendamentos')

    cliente = models.ForeignKey(
        'Client', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='agendamentos'
    )

    servico = models.ForeignKey('Service', on_delete=models.PROTECT, related_name='agendamentos')

    inicio = models.DateTimeField()
    fim = models.DateTimeField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmado')
    criado_via = models.CharField(max_length=20, choices=ORIGEM_CHOICES, default='manual')

    valor_no_momento = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True, blank=True,  # <- deixa passar vazio no form
        help_text='Preço congelado na data em que o agendamento foi criado.'
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # calcula fim automaticamente
        if self.inicio and self.servico_id:
            dur = self.servico.duracao_minutos or 30
            self.fim = self.inicio + timedelta(minutes=dur)

        # garante valor_no_momento
        if self.servico_id and (self.valor_no_momento is None or self.valor_no_momento == ''):
            self.valor_no_momento = self.servico.preco

        super().save(*args, **kwargs)

    def _str_(self):
        return f'{self.servico.nome} - {self.inicio} ({self.get_status_display()})'

class Cancellation(models.Model):
    """
    Registro de cancelamento aprovado.
    """
    MOTIVO_CHOICES = [
        ('cliente', 'Cliente'),
        ('barbearia', 'Barbearia'),
    ]

    agendamento = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='cancelamento'
    )
    motivo = models.CharField(max_length=20, choices=MOTIVO_CHOICES)
    observacao = models.TextField(blank=True, null=True)
    aprovado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Cancelamento #{self.agendamento_id}'

# ==========================
# ASSINATURA / PLANOS (V1 / V2)
# ==========================
class PlanSubscription(models.Model):
    PLAN_V1 = "V1"
    PLAN_V2 = "V2"
    PLAN_CHOICES = [
        (PLAN_V1, "V1 — Essencial"),
        (PLAN_V2, "V2 — Premium"),
    ]

    shop = models.OneToOneField(BarberShop, on_delete=models.CASCADE, related_name="subscription")

    # Plano atualmente ativo
    current_plan = models.CharField(max_length=2, choices=PLAN_CHOICES, default=PLAN_V1)

    # Se o cliente clicou pra trocar de plano (e ainda não foi confirmado)
    requested_plan = models.CharField(max_length=2, choices=PLAN_CHOICES, blank=True, null=True)

    # Data de vencimento (opcional – útil pra você mostrar no painel)
    next_due_date = models.DateField(blank=True, null=True)

    # Isenções (Marquinhos e outros “VIPs”)
    is_exempt = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Assinatura {self.current_plan} — {self.shop.nome}"


class RecurringBlock(models.Model):
    '''
    Bloqueios recorrentes na agenda (ex.: cliente fixo toda terça 10:00,
    ou pausa de almoço toda quarta 12:00–15:00).

    Efeito:
    - NÃO aparece para o público como horário disponível
    - Aparece na visão semanal do dono (como "FIXO" ou "PAUSA")
    '''

    KIND_CHOICES = (
        ("fixo", "Cliente fixo"),
        ("pausa", "Pausa"),
    )

    barbearia = models.ForeignKey(BarberShop, on_delete=models.CASCADE, related_name="recurring_blocks")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="fixo")

    titulo = models.CharField(max_length=80, help_text="Ex.: João (pacote) / Almoço / Reunião")
    dia_semana = models.IntegerField(
        choices=(
            (0, "Segunda"),
            (1, "Terça"),
            (2, "Quarta"),
            (3, "Quinta"),
            (4, "Sexta"),
            (5, "Sábado"),
            (6, "Domingo"),
        ),
        help_text="Dia da semana do bloqueio",
    )
    inicio = models.TimeField()
    fim = models.TimeField()

    servico = models.ForeignKey(Service, null=True, blank=True, on_delete=models.SET_NULL)
    duracao_minutos = models.PositiveIntegerField(null=True, blank=True, help_text="Opcional (para FIXO)")

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("dia_semana", "inicio", "fim", "titulo")

    def __str__(self):
        return f"{self.get_kind_display()} • {self.titulo} • {self.get_dia_semana_display()} {self.inicio}-{self.fim}"
