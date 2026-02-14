import re


import json
from datetime import datetime, timedelta, date

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Avg, Count, Value
from django.db.models.functions import Coalesce, TruncDate, ExtractHour
from django.db.models import DecimalField
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from urllib.parse import quote

from .models import (
    Appointment,
    BarberShop,
    WorkDayConfig,
    Client,
    Service,
    Product,
    ProductSale,
    PlanSubscription,
    RecurringBlock,
)


# =========================
# UTIL (telefone - portal público)
# =========================

def _digits_only(value):
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def _client_ids_by_phone(barbearia, telefone_raw):
    # Retorna IDs de clientes (da barbearia) com o mesmo telefone, ignorando máscara.
    digits = _digits_only(telefone_raw)
    if not digits:
        return []
    ids = []
    for c in Client.objects.filter(barbearia=barbearia).exclude(telefone__isnull=True).exclude(telefone=""):
        if _digits_only(c.telefone) == digits:
            ids.append(c.id)
    return ids


def _get_or_create_client_by_phone(barbearia, nome, telefone_raw):
    # Reusa cliente existente pelo telefone (ignorando máscara) ou cria um novo.
    tel_digits = _digits_only(telefone_raw)
    ids = _client_ids_by_phone(barbearia, tel_digits)
    cliente = Client.objects.filter(id__in=ids).order_by('-id').first()
    if cliente:
        changed = False
        if tel_digits and cliente.telefone != tel_digits:
            cliente.telefone = tel_digits
            changed = True
        if nome and cliente.nome != nome:
            cliente.nome = nome
            changed = True
        if changed:
            cliente.save(update_fields=['nome', 'telefone'])
        return cliente
    return Client.objects.create(barbearia=barbearia, nome=nome or 'Cliente', telefone=tel_digits)
from .forms import (
    SignupEstabelecimentoForm,
    NovoAgendamentoForm,
    CancelamentoForm,
    RemarcarAgendamentoForm,
    PublicEscolherServicoForm,
    PublicConfirmarDadosForm,
    PublicClienteLoginForm,
    ServiceForm,
    ProductForm,
    ProductSaleForm,
    WorkDayConfigForm,
    RecurringBlockForm,
)

DECIMAL0 = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))

from django.shortcuts import get_object_or_404
from .models import BarberShop

def get_shop_or_403(request, slug):
    return get_object_or_404(
        BarberShop,
        slug=slug,
        dono=request.user
    )

from django.contrib.auth import logout
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

@require_POST
def sair(request):
    logout(request)
    return redirect("login")  # ou sua home


@login_required
@require_POST
def confirmar_agendamento(request, agendamento_id):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    agendamento = get_object_or_404(Appointment, id=agendamento_id, barbearia=barbearia)

    if agendamento.status == 'cancelado':
        messages.warning(request, 'Esse agendamento já está cancelado.')
    else:
        agendamento.status = 'confirmado'
        agendamento.save(update_fields=['status'])
        messages.success(request, 'Atendimento confirmado! Agora ele conta no financeiro.')

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    return redirect(next_url or 'homemcom_dashboard')

# ==========================
# HELPERS (MULTI-TENANT)
# ==========================

def _normalize_phone_to_wa(phone: str | None) -> str | None:
    """
    Recebe telefone em qualquer formato e devolve só dígitos no padrão wa.me.
    Regra simples:
      - remove tudo que não for dígito
      - se tiver 11 ou 10 dígitos, assume BR e prefixa 55
    """
    if not phone:
        return None
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if not digits:
        return None
    if len(digits) in (10, 11):
        digits = "55" + digits
    return digits


def _get_active_shop(request):
    """
    Multi-tenant simples:
      - cada usuário pode ter 1+ barbearias
      - usa session['active_shop_id'] se existir
      - caso contrário, pega a primeira do usuário e grava na sessão
    """
    if not request.user.is_authenticated:
        return None
    qs = BarberShop.objects.filter(dono=request.user).order_by("id")
    shop_id = request.session.get("active_shop_id")
    if shop_id:
        shop = qs.filter(id=shop_id).first()
        if shop:
            return shop
    shop = qs.first()
    if shop:
        request.session["active_shop_id"] = shop.id
    return shop


def _require_shop(request):
    shop = _get_active_shop(request)
    if not shop:
        return None, redirect("signup")
    return shop, None


# ==========================
# DASHBOARD (LOGADO)
# ==========================

@login_required
def dashboard(request):
    # Splash (loading) 1x por sessão
    if not request.GET.get("noload") and not request.session.get("kairos_loading_seen"):
        request.session["kairos_loading_seen"] = True
        return render(
            request,
            "agenda/loading.html",
            {"next_url": reverse("homemcom_dashboard") + "?noload=1"},
        )

    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    hoje = timezone.localdate()

    # Agendamentos do dia
    agendamentos_hoje = (
        Appointment.objects.filter(barbearia=barbearia, inicio__date=hoje)
        .select_related("cliente", "servico")
        .order_by("inicio")
    )

    confirmados_hoje = agendamentos_hoje.filter(status="confirmado")

    # SERVIÇOS (DIA)
    total_atendimentos_hoje = confirmados_hoje.count()
    total_servicos_hoje = (
        confirmados_hoje.aggregate(total=Coalesce(Sum("valor_no_momento"), DECIMAL0))["total"]
        or 0
    )
    ticket_medio_hoje = (
        confirmados_hoje.aggregate(media=Coalesce(Avg("valor_no_momento"), DECIMAL0))["media"]
        or 0
    )

    # PRODUTOS (DIA)
    vendas_produtos_hoje = ProductSale.objects.filter(
        barbearia=barbearia, data_hora__date=hoje
    )
    total_produtos_hoje = (
        vendas_produtos_hoje.aggregate(total=Coalesce(Sum("valor_total"), DECIMAL0))["total"]
        or 0
    )
    qtd_produtos_hoje = (
        vendas_produtos_hoje.aggregate(total=Coalesce(Sum("quantidade"), Value(0)))["total"]
        or 0
    )

    # TOTAL DIA
    total_valor_hoje = float(total_servicos_hoje) + float(total_produtos_hoje)

    # SEMANA
    inicio_semana = hoje - timedelta(days=hoje.weekday())  # segunda
    fim_semana = inicio_semana + timedelta(days=6)  # domingo

    confirmados_semana = Appointment.objects.filter(
        barbearia=barbearia,
        status="confirmado",
        inicio__date__gte=inicio_semana,
        inicio__date__lte=fim_semana,
    )

    total_servicos_semana = (
        confirmados_semana.aggregate(total=Coalesce(Sum("valor_no_momento"), DECIMAL0))["total"]
        or 0
    )

    vendas_produtos_semana = ProductSale.objects.filter(
        barbearia=barbearia,
        data_hora__date__gte=inicio_semana,
        data_hora__date__lte=fim_semana,
    )
    total_produtos_semana = (
        vendas_produtos_semana.aggregate(total=Coalesce(Sum("valor_total"), DECIMAL0))["total"]
        or 0
    )
    qtd_produtos_semana = (
        vendas_produtos_semana.aggregate(total=Coalesce(Sum("quantidade"), Value(0)))["total"]
        or 0
    )

    total_valor_semana = float(total_servicos_semana) + float(total_produtos_semana)

    # MÊS
    confirmados_mes = Appointment.objects.filter(
        barbearia=barbearia,
        status="confirmado",
        inicio__year=hoje.year,
        inicio__month=hoje.month,
    )
    total_servicos_mes = (
        confirmados_mes.aggregate(total=Coalesce(Sum("valor_no_momento"), DECIMAL0))["total"]
        or 0
    )

    vendas_produtos_mes = ProductSale.objects.filter(
        barbearia=barbearia,
        data_hora__year=hoje.year,
        data_hora__month=hoje.month,
    )
    total_produtos_mes = (
        vendas_produtos_mes.aggregate(total=Coalesce(Sum("valor_total"), DECIMAL0))["total"]
        or 0
    )
    qtd_produtos_mes = (
        vendas_produtos_mes.aggregate(total=Coalesce(Sum("quantidade"), Value(0)))["total"]
        or 0
    )

    total_valor_mes = float(total_servicos_mes) + float(total_produtos_mes)

    # CANCELADOS DO DIA (só serviços)
    cancelados_hoje = Appointment.objects.filter(
        barbearia=barbearia, status="cancelado", inicio__date=hoje
    )
    total_cancelado_hoje = (
        cancelados_hoje.aggregate(total=Coalesce(Sum("valor_no_momento"), DECIMAL0))["total"]
        or 0
    )

    # TOP SERVIÇOS (SEMANA)
    top_servicos_semana_raw = (
        Appointment.objects.filter(
            barbearia=barbearia,
            status="confirmado",
            inicio__date__gte=inicio_semana,
            inicio__date__lte=fim_semana,
        )
        .values("servico__nome")
        .annotate(qtd=Count("id"), total=Coalesce(Sum("valor_no_momento"), DECIMAL0))
        .order_by("-qtd", "-total")[:5]
    )
    top_servicos_semana = [
        {"nome": r["servico__nome"] or "—", "qtd": int(r["qtd"] or 0), "total": f"{float(r['total'] or 0):.2f}"}
        for r in top_servicos_semana_raw
    ]

    # TOP PRODUTOS (SEMANA)
    top_produtos_semana_raw = (
        vendas_produtos_semana.annotate(
            nome_p=Coalesce("produto__nome", "produto_nome", Value("—"))
        )
        .values("nome_p")
        .annotate(qtd=Coalesce(Sum("quantidade"), Value(0)), receita=Coalesce(Sum("valor_total"), DECIMAL0))
        .order_by("-receita", "-qtd")[:5]
    )
    top_produtos_semana = [
        {"nome": r["nome_p"], "qtd": int(r["qtd"] or 0), "receita": f"{float(r['receita'] or 0):.2f}"}
        for r in top_produtos_semana_raw
    ]

    # INSIGHTS (crescimento semanal vs semana anterior)
    inicio_semana_ant = inicio_semana - timedelta(days=7)
    fim_semana_ant = fim_semana - timedelta(days=7)

    total_semana_ant_serv = (
        Appointment.objects.filter(
            barbearia=barbearia,
            status="confirmado",
            inicio__date__gte=inicio_semana_ant,
            inicio__date__lte=fim_semana_ant,
        ).aggregate(total=Coalesce(Sum("valor_no_momento"), DECIMAL0))["total"]
        or 0
    )
    total_semana_ant_prod = (
        ProductSale.objects.filter(
            barbearia=barbearia,
            data_hora__date__gte=inicio_semana_ant,
            data_hora__date__lte=fim_semana_ant,
        ).aggregate(total=Coalesce(Sum("valor_total"), DECIMAL0))["total"]
        or 0
    )
    total_semana_ant = float(total_semana_ant_serv) + float(total_semana_ant_prod)

    crescimento_semana_pct = None
    if total_semana_ant > 0:
        crescimento_semana_pct = ((total_valor_semana - total_semana_ant) / total_semana_ant) * 100

    crescimento_servicos_semana_pct = None
    if float(total_semana_ant_serv) > 0:
        crescimento_servicos_semana_pct = ((float(total_servicos_semana) - float(total_semana_ant_serv)) / float(total_semana_ant_serv)) * 100

    crescimento_produtos_semana_pct = None
    if float(total_semana_ant_prod) > 0:
        crescimento_produtos_semana_pct = ((float(total_produtos_semana) - float(total_semana_ant_prod)) / float(total_semana_ant_prod)) * 100

    total_ag_hoje = agendamentos_hoje.count()
    taxa_cancelamento_hoje = (
        (agendamentos_hoje.filter(status="cancelado").count() / total_ag_hoje * 100) if total_ag_hoje else 0
    )

    total_ag_semana = Appointment.objects.filter(
        barbearia=barbearia,
        inicio__date__gte=inicio_semana,
        inicio__date__lte=fim_semana,
    ).count()
    cancel_semana = Appointment.objects.filter(
        barbearia=barbearia,
        status="cancelado",
        inicio__date__gte=inicio_semana,
        inicio__date__lte=fim_semana,
    ).count()
    taxa_cancelamento_semana = (cancel_semana / total_ag_semana * 100) if total_ag_semana else 0

    # pico horário (semana)
    pico_hora = None
    pico_qtd = 0
    pico_raw = (
        confirmados_semana.annotate(hora=ExtractHour("inicio"))
        .values("hora")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")
        .first()
    )
    if pico_raw and pico_raw.get("hora") is not None:
        pico_hora = int(pico_raw["hora"])
        pico_qtd = int(pico_raw["qtd"] or 0)

    # ocupação estimada (minutos agendados / minutos disponíveis)
    minutos_disponiveis = 0
    for i in range(7):
        dia_ref = inicio_semana + timedelta(days=i)
        for cfg in WorkDayConfig.objects.filter(
            barbearia=barbearia, dia_semana=dia_ref.weekday(), ativo=True
        ):
            delta = datetime.combine(dia_ref, cfg.fim) - datetime.combine(dia_ref, cfg.inicio)
            minutos_disponiveis += int(delta.total_seconds() // 60)

    minutos_agendados = 0
    for ag in confirmados_semana.select_related("servico"):
        minutos_agendados += int((ag.servico.duracao_minutos or 30))

    ocupacao_semana_pct = (minutos_agendados / minutos_disponiveis * 100) if minutos_disponiveis else 0

    # textos rápidos (dashboard inteligente)
    if top_servicos_semana:
        s0 = top_servicos_semana[0]
        insight_melhor_servico_semana = f"{s0['nome']} lidera na semana ({s0['qtd']} atend.)"
    else:
        insight_melhor_servico_semana = "Sem serviços confirmados na semana ainda"

    if top_produtos_semana:
        p0 = top_produtos_semana[0]
        insight_produto_top_semana = f"{p0['nome']} é o campeão ({p0['qtd']} un.)"
    else:
        insight_produto_top_semana = "Sem vendas de produto na semana"

    if pico_hora is not None and pico_qtd:
        insight_pico_horario_semana = f"Pico por volta das {pico_hora:02d}h ({pico_qtd} agend.)"
    else:
        insight_pico_horario_semana = "Pico de horário ainda não definido"

    insight_taxa_cancelamento = f"Cancelamentos: {taxa_cancelamento_hoje:.0f}% hoje | {taxa_cancelamento_semana:.0f}% semana"

    # Série: receita últimos 14 dias (serviços e produtos)
    inicio_14 = hoje - timedelta(days=13)

    serv_por_dia = {
        r["dia"]: float(r["total"] or 0)
        for r in (
            Appointment.objects.filter(
                barbearia=barbearia,
                status="confirmado",
                inicio__date__gte=inicio_14,
                inicio__date__lte=hoje,
            )
            .annotate(dia=TruncDate("inicio"))
            .values("dia")
            .annotate(total=Coalesce(Sum("valor_no_momento"), DECIMAL0))
        )
    }

    prod_por_dia = {
        r["dia"]: float(r["total"] or 0)
        for r in (
            ProductSale.objects.filter(
                barbearia=barbearia,
                data_hora__date__gte=inicio_14,
                data_hora__date__lte=hoje,
            )
            .annotate(dia=TruncDate("data_hora"))
            .values("dia")
            .annotate(total=Coalesce(Sum("valor_total"), DECIMAL0))
        )
    }

    labels_14, serie_serv, serie_prod = [], [], []
    d = inicio_14
    while d <= hoje:
        labels_14.append(d.strftime("%d/%m"))
        serie_serv.append(serv_por_dia.get(d, 0.0))
        serie_prod.append(prod_por_dia.get(d, 0.0))
        d += timedelta(days=1)

    chart_payload = {"labels": labels_14, "servicos": serie_serv, "produtos": serie_prod}

    context = {
        "barbearia": barbearia,
        "data_hoje": hoje,
        "agendamentos_hoje": agendamentos_hoje,
        "total_atendimentos_hoje": total_atendimentos_hoje,
        "total_valor_hoje": f"{total_valor_hoje:.2f}",
        "ticket_medio_hoje": f"{float(ticket_medio_hoje):.2f}",
        "total_valor_semana": f"{total_valor_semana:.2f}",
        "total_valor_mes": f"{total_valor_mes:.2f}",
        "total_cancelado_hoje": f"{float(total_cancelado_hoje):.2f}",
        "total_servicos_hoje": f"{float(total_servicos_hoje):.2f}",
        "total_produtos_hoje": f"{float(total_produtos_hoje):.2f}",
        "qtd_produtos_hoje": int(qtd_produtos_hoje or 0),
        "total_servicos_semana": f"{float(total_servicos_semana):.2f}",
        "total_produtos_semana": f"{float(total_produtos_semana):.2f}",
        "qtd_produtos_semana": int(qtd_produtos_semana or 0),
        "total_servicos_mes": f"{float(total_servicos_mes):.2f}",
        "total_produtos_mes": f"{float(total_produtos_mes):.2f}",
        "qtd_produtos_mes": int(qtd_produtos_mes or 0),
        "inicio_semana": inicio_semana,
        "fim_semana": fim_semana,
        "top_servicos_semana": top_servicos_semana,
        "top_produtos_semana": top_produtos_semana,
        # indicadores inteligentes
        "crescimento_semana_pct": crescimento_semana_pct,
        "crescimento_servicos_semana_pct": crescimento_servicos_semana_pct,
        "crescimento_produtos_semana_pct": crescimento_produtos_semana_pct,
        "taxa_cancelamento_hoje": taxa_cancelamento_hoje,
        "taxa_cancelamento_semana": taxa_cancelamento_semana,
        "ocupacao_semana_pct": ocupacao_semana_pct,
        "insight_melhor_servico_semana": insight_melhor_servico_semana,
        "insight_produto_top_semana": insight_produto_top_semana,
        "insight_pico_horario_semana": insight_pico_horario_semana,
        "insight_taxa_cancelamento": insight_taxa_cancelamento,
        "chart_payload_json": json.dumps(chart_payload),
    }
    return render(request, "agenda/homemcom_dashboard.html", context)


@login_required
def novo_agendamento(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    if request.method == "POST":
        form = NovoAgendamentoForm(request.POST, barbearia=barbearia)
        if form.is_valid():
            form.save(barbearia=barbearia)
            messages.success(request, "Agendamento criado com sucesso!")
            return redirect("homemcom_dashboard")
    else:
        agora = timezone.localtime()
        form = NovoAgendamentoForm(
            barbearia=barbearia,
            initial={"inicio": agora.replace(second=0, microsecond=0)},
        )

    return render(
        request,
        "agenda/novo_agendamento.html",
        {"form": form, "barbearia": barbearia},
    )


@login_required
def relatorios_view(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    hoje = timezone.localdate()

    def parse_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    def month_range(d: date):
        inicio = d.replace(day=1)
        if d.month == 12:
            prox = date(d.year + 1, 1, 1)
        else:
            prox = date(d.year, d.month + 1, 1)
        fim = prox - timedelta(days=1)
        return inicio, fim

    periodo = request.GET.get("periodo", "mes")  # hoje | 7d | 30d | mes | custom
    inicio_str = request.GET.get("inicio")
    fim_str = request.GET.get("fim")

    if periodo == "hoje":
        data_inicio = hoje
        data_fim = hoje
    elif periodo == "7d":
        data_inicio = hoje - timedelta(days=6)
        data_fim = hoje
    elif periodo == "30d":
        data_inicio = hoje - timedelta(days=29)
        data_fim = hoje
    elif periodo == "custom":
        data_inicio = parse_date(inicio_str) or hoje
        data_fim = parse_date(fim_str) or hoje
    else:
        data_inicio, data_fim = month_range(hoje)

    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    qs_base = Appointment.objects.filter(
        barbearia=barbearia,
        inicio__date__gte=data_inicio,
        inicio__date__lte=data_fim,
    )
    qs_confirmados = qs_base.filter(status="confirmado")
    qs_cancelados = qs_base.filter(status="cancelado")

    kpi_agendamentos = qs_base.count()
    kpi_confirmados = qs_confirmados.count()
    kpi_cancelados = qs_cancelados.count()

    total_servicos = qs_confirmados.aggregate(total=Coalesce(Sum("valor_no_momento"), DECIMAL0))["total"] or 0
    qs_produtos = ProductSale.objects.filter(
        barbearia=barbearia,
        data_hora__date__gte=data_inicio,
        data_hora__date__lte=data_fim,
    )
    total_produtos = qs_produtos.aggregate(total=Coalesce(Sum("valor_total"), DECIMAL0))["total"] or 0
    qtd_produtos = qs_produtos.aggregate(total=Coalesce(Sum("quantidade"), Value(0)))["total"] or 0

    receita_total = float(total_servicos) + float(total_produtos)

    def brl(v: float) -> str:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    kpi_receita = brl(receita_total)
    kpi_produtos_receita = brl(float(total_produtos))

    top_raw = (
        qs_confirmados.values("servico__nome")
        .annotate(qtd=Count("id"), receita=Coalesce(Sum("valor_no_momento"), DECIMAL0))
        .order_by("-qtd", "-receita")[:8]
    )
    top_servicos = [
        {"nome": r["servico__nome"], "qtd": int(r["qtd"]), "receita": brl(float(r["receita"] or 0))}
        for r in top_raw
    ]

    top_produtos_raw = (
        qs_produtos.annotate(
            nome_p=Coalesce("produto__nome", "produto_nome", Value("—"))
        )
        .values("nome_p")
        .annotate(qtd=Coalesce(Sum("quantidade"), Value(0)), receita=Coalesce(Sum("valor_total"), DECIMAL0))
        .order_by("-receita", "-qtd")[:8]
    )
    top_produtos = [
        {"nome": r["nome_p"], "qtd": int(r["qtd"] or 0), "receita": brl(float(r["receita"] or 0))}
        for r in top_produtos_raw
    ]

    kpi_itens_produtos = qs_produtos.aggregate(total=Coalesce(Sum("quantidade"), Value(0)))["total"] or 0
    kpi_produtos_distintos = qs_produtos.values("produto_id").distinct().count()

    produtos_detalhados_raw = (
        qs_produtos.annotate(
            nome_p=Coalesce("produto__nome", "produto_nome", Value("—"))
        )
        .values("nome_p")
        .annotate(qtd=Coalesce(Sum("quantidade"), Value(0)), receita=Coalesce(Sum("valor_total"), DECIMAL0))
        .order_by("-receita", "-qtd", "nome_p")
    )
    produtos_detalhados = [
        {"nome": r["nome_p"], "qtd": int(r["qtd"] or 0), "receita": brl(float(r["receita"] or 0))}
        for r in produtos_detalhados_raw
    ]

    resumo_por_dia = []
    dia = data_inicio
    while dia <= data_fim:
        dia_qs = qs_base.filter(inicio__date=dia)
        resumo_por_dia.append(
            {
                "dia": dia.strftime("%d/%m"),
                "agendamentos": dia_qs.count(),
                "confirmados": dia_qs.filter(status="confirmado").count(),
                "cancelados": dia_qs.filter(status="cancelado").count(),
            }
        )
        dia += timedelta(days=1)

    context = {
        "barbearia": barbearia,
        "hoje": hoje,
        "periodo": periodo,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "kpi_agendamentos": kpi_agendamentos,
        "kpi_confirmados": kpi_confirmados,
        "kpi_cancelados": kpi_cancelados,
        "kpi_receita": kpi_receita,
        "kpi_itens_produtos": int(kpi_itens_produtos or 0),
        "kpi_produtos_distintos": kpi_produtos_distintos,
        "kpi_produtos_qtd": int(qtd_produtos or 0),
        "kpi_produtos_receita": kpi_produtos_receita,
        "top_servicos": top_servicos,
        "top_produtos": top_produtos,
        "produtos_detalhados": produtos_detalhados,
        "resumo_por_dia": resumo_por_dia,
    }
    return render(request, "agenda/relatorios.html", context)


@login_required
def cancelar_agendamento(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    agendamento = get_object_or_404(Appointment, pk=pk, barbearia=barbearia)

    if agendamento.status == "cancelado":
        messages.info(request, "Este agendamento já está cancelado.")
        return redirect("homemcom_dashboard")

    if request.method == "POST":
        form = CancelamentoForm(request.POST)
        if form.is_valid():
            cancelamento = form.save(commit=False)
            cancelamento.agendamento = agendamento
            cancelamento.aprovado_por = request.user
            cancelamento.save()

            agendamento.status = "cancelado"
            agendamento.save()

            messages.success(request, "Agendamento cancelado com sucesso.")
            return redirect("homemcom_dashboard")
    else:
        form = CancelamentoForm()

    return render(
        request,
        "agenda/cancelar_agendamento.html",
        {"form": form, "agendamento": agendamento, "barbearia": barbearia},
    )


@login_required
def remarcar_agendamento(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    agendamento = get_object_or_404(Appointment, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = RemarcarAgendamentoForm(request.POST, instance=agendamento)
        if form.is_valid():
            form.save()
            messages.success(request, "Agendamento remarcado com sucesso.")
            return redirect("homemcom_dashboard")
    else:
        form = RemarcarAgendamentoForm(instance=agendamento, initial={"inicio": agendamento.inicio})

    return render(
        request,
        "agenda/remarcar_agendamento.html",
        {"form": form, "agendamento": agendamento, "barbearia": barbearia},
    )


# ==========================
# VISÃO SEMANAL
# ==========================

from datetime import datetime, timedelta
from django.utils import timezone

# from .models import RecurringBlock


def _slot_colide_com_bloqueio(slot_inicio, slot_fim, b_inicio, b_fim):
    # colisão simples: [slot_inicio, slot_fim) cruza com [b_inicio, b_fim)
    return (slot_inicio < b_fim) and (slot_fim > b_inicio)


def aplicar_bloqueios_recorrentes(barbearia, data, horarios, duracao_minutos):
    """
    horarios: lista de datetimes (início de cada slot)
    duracao_minutos: duração do serviço (int)
    Retorna a lista filtrada removendo horários que caem em RecurringBlock (pausas/cliente fixo).
    """
    dow = data.weekday()
    blocos = RecurringBlock.objects.filter(barbearia=barbearia, ativo=True, dia_semana=dow)

    tz = timezone.get_current_timezone()
    dur = timedelta(minutes=duracao_minutos or 30)

    filtrados = []
    for h in horarios:
        # h pode ser naive dependendo do seu gerador; garantimos aware
        slot_inicio = timezone.make_aware(h, tz) if timezone.is_naive(h) else h
        slot_fim = slot_inicio + dur

        bloqueado = False
        for b in blocos:
            b_inicio_dt = timezone.make_aware(datetime.combine(data, b.inicio), tz)
            b_fim_dt = timezone.make_aware(datetime.combine(data, b.fim), tz)

            if _slot_colide_com_bloqueio(slot_inicio, slot_fim, b_inicio_dt, b_fim_dt):
                bloqueado = True
                break

        if not bloqueado:
            filtrados.append(slot_inicio)

    return filtrados

@login_required
def semana_view(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    hoje = timezone.localdate()

    ref_str = request.GET.get("ref")
    if ref_str:
        try:
            ref_date = datetime.fromisoformat(ref_str).date()
        except ValueError:
            ref_date = hoje
    else:
        ref_date = hoje

    inicio_semana = ref_date - timedelta(days=ref_date.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    prev_ref = inicio_semana - timedelta(days=7)
    next_ref = inicio_semana + timedelta(days=7)

    # ✅ puxa bloqueios ativos 1 vez
    bloqueios_ativos = list(
        RecurringBlock.objects.filter(barbearia=barbearia, ativo=True)
        .order_by("dia_semana", "inicio")
    )

    dias_semana = []
    for i in range(7):
        data = inicio_semana + timedelta(days=i)

        agendamentos = (
            Appointment.objects.filter(barbearia=barbearia, inicio__date=data)
            .select_related("cliente", "servico")
            .order_by("inicio")
        )

        total_dia = (
            agendamentos.filter(status="confirmado").aggregate(
                total=Coalesce(Sum("valor_no_momento"), DECIMAL0)
            )["total"]
            or 0
        )

        dow = data.weekday()  # 0=Seg ... 6=Dom
        bloqueios = []
        for b in bloqueios_ativos:
            if b.dia_semana != dow:
                continue

            bloqueios.append(
                {
                    "kind": b.kind,
                    "titulo": b.titulo,
                    "inicio": b.inicio,
                    "fim": b.fim,
                }
            )

        dias_semana.append(
            {
                "data": data,
                "agendamentos": agendamentos,
                "total_dia": total_dia,
                "bloqueios": bloqueios,
            }
        )

    context = {
        "barbearia": barbearia,
        "hoje": hoje,
        "inicio_semana": inicio_semana,
        "fim_semana": fim_semana,
        "dias_semana": dias_semana,
        "prev_ref": prev_ref,
        "next_ref": next_ref,
        "ref_date": ref_date,
    }
    return render(request, "agenda/semana.html", context)

# ==========================
# CONFIGURAÇÕES
# ==========================

@login_required
def configuracoes_view(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    servicos = Service.objects.filter(barbearia=barbearia).order_by("nome")
    produtos = Product.objects.filter(barbearia=barbearia).order_by("nome")
    horarios = WorkDayConfig.objects.filter(barbearia=barbearia, ativo=True).order_by(
        "dia_semana", "inicio"
    )

    return render(
        request,
        "agenda/configuracoes.html",
        {"barbearia": barbearia, "servicos": servicos, "produtos": produtos, "horarios": horarios},
    )


@login_required
def novo_servico(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    if request.method == "POST":
        form = ServiceForm(request.POST)
        if form.is_valid():
            servico = form.save(commit=False)
            servico.barbearia = barbearia
            servico.save()
            messages.success(request, "Serviço criado com sucesso.")
            return redirect("homemcom_configuracoes")
    else:
        form = ServiceForm()

    return render(
        request,
        "agenda/editar_servico.html",
        {"form": form, "barbearia": barbearia, "titulo": "Novo serviço"},
    )


@login_required
def editar_servico(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    servico = get_object_or_404(Service, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = ServiceForm(request.POST, instance=servico)
        if form.is_valid():
            form.save()
            messages.success(request, "Serviço atualizado com sucesso.")
            return redirect("homemcom_configuracoes")
    else:
        form = ServiceForm(instance=servico)

    return render(
        request,
        "agenda/editar_servico.html",
        {"form": form, "barbearia": barbearia, "titulo": f"Editar serviço: {servico.nome}"},
    )


@login_required
def novo_produto(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            produto = form.save(commit=False)
            produto.barbearia = barbearia
            produto.save()
            messages.success(request, "Produto criado com sucesso.")
            return redirect("homemcom_configuracoes")
    else:
        form = ProductForm()

    return render(
        request,
        "agenda/editar_produto.html",
        {"form": form, "barbearia": barbearia, "titulo": "Novo produto"},
    )


@login_required
def editar_produto(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    produto = get_object_or_404(Product, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=produto)
        if form.is_valid():
            form.save()
            messages.success(request, "Produto atualizado com sucesso.")
            return redirect("homemcom_configuracoes")
    else:
        form = ProductForm(instance=produto)

    return render(
        request,
        "agenda/editar_produto.html",
        {"form": form, "barbearia": barbearia, "titulo": f"Editar produto: {produto.nome}"},
    )

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required

# se você já tem isso, mantém
# def _require_shop(request): ...

@login_required
def excluir_servico(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    servico = get_object_or_404(Service, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        # "Excluir" SaaS = desativar
        servico.ativo = False
        servico.save(update_fields=["ativo"])
        messages.success(request, f"Serviço “{servico.nome}” desativado com sucesso.")
        return redirect("homemcom_configuracoes")

    return render(
        request,
        "agenda/confirmar_exclusao.html",
        {
            "barbearia": barbearia,
            "objeto": servico,
            "tipo": "serviço",
            "voltar_url": "homemcom_configuracoes",
            "confirm_url_name": "homemcom_excluir_servico",
        },
    )


@login_required
def excluir_produto(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    produto = get_object_or_404(Product, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        produto.ativo = False
        produto.save(update_fields=["ativo"])
        messages.success(request, f"Produto “{produto.nome}” desativado com sucesso.")
        return redirect("homemcom_configuracoes")

    return render(
        request,
        "agenda/confirmar_exclusao.html",
        {
            "barbearia": barbearia,
            "objeto": produto,
            "tipo": "produto",
            "voltar_url": "homemcom_configuracoes",
            "confirm_url_name": "homemcom_excluir_produto",
        },
    )

# ==========================
# REGISTRAR VENDA DE PRODUTO
# ==========================

@login_required
def registrar_venda_produto(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    produtos = Product.objects.filter(barbearia=barbearia, ativo=True).order_by("nome")

    if request.method == "POST":
        form = ProductSaleForm(request.POST, barbearia=barbearia)
        if form.is_valid():
            form.save(barbearia=barbearia)
            messages.success(request, "Venda registrada com sucesso.")
            return redirect("homemcom_dashboard")
        messages.error(request, "Ops! Revise os campos da venda.")
    else:
        form = ProductSaleForm(barbearia=barbearia)

    return render(
        request,
        "agenda/registrar_venda_produto.html",
        {"form": form, "barbearia": barbearia, "produtos": produtos},
    )


# ==========================
# LÓGICA DE HORÁRIOS LIVRES
# ==========================




def _is_slot_blocked_by_recurring(barbearia, dia_ref, slot_inicio, slot_fim) -> bool:
    """True se [slot_inicio, slot_fim) colidir com algum RecurringBlock ativo."""
    weekday = dia_ref.weekday()
    blocks = RecurringBlock.objects.filter(barbearia=barbearia, ativo=True, dia_semana=weekday)
    for b in blocks:
        if (slot_inicio < b.fim) and (slot_fim > b.inicio):
            return True
    return False


def gerar_horarios_disponiveis(barbearia, servico, data):
    configs = WorkDayConfig.objects.filter(
        barbearia=barbearia, dia_semana=data.weekday(), ativo=True
    ).order_by("inicio")

    if not configs.exists():
        return []

    tz = timezone.get_current_timezone()
    duracao = timedelta(minutes=servico.duracao_minutos or 30)

    agendamentos = Appointment.objects.filter(
        barbearia=barbearia, inicio__date=data
    ).exclude(status="cancelado")

    horarios_livres = []

    for config in configs:
        inicio_bloco = timezone.make_aware(datetime.combine(data, config.inicio), tz)
        fim_bloco = timezone.make_aware(datetime.combine(data, config.fim), tz)

        inicio = inicio_bloco
        while inicio + duracao <= fim_bloco:
            fim = inicio + duracao
            conflito = agendamentos.filter(inicio__lt=fim, fim__gt=inicio).exists()
            # Bloqueios recorrentes (clientes fixos / pausas) também ocupam o horário
            bloqueado = _is_slot_blocked_by_recurring(
                barbearia,
                data,
                inicio.time(),
                fim.time(),
            )

            if (not conflito) and (not bloqueado):
                horarios_livres.append(inicio)
            inicio += duracao

    return horarios_livres


# ==========================
# ÁREA PÚBLICA (CLIENTE)
# ==========================

def public_escolher_servico(request, slug):
    barbearia = get_object_or_404(BarberShop, slug=slug)

    if request.method == "POST":
        form = PublicEscolherServicoForm(request.POST, barbearia=barbearia)
        if form.is_valid():
            servico = form.cleaned_data["servico"]
            data = form.cleaned_data["data"]
            return redirect(f"/agendar/{slug}/horarios/?servico={servico.id}&data={data.isoformat()}")
    else:
        hoje = timezone.localdate()
        form = PublicEscolherServicoForm(barbearia=barbearia, initial={"data": hoje})

    return render(request, "agenda/public_escolher_servico.html", {"form": form, "barbearia": barbearia})


def public_escolher_horario(request, slug):
    barbearia = get_object_or_404(BarberShop, slug=slug)

    servico_id = request.GET.get("servico")
    data_str = request.GET.get("data")

    try:
        servico = Service.objects.get(id=servico_id, barbearia=barbearia, ativo=True)
    except Service.DoesNotExist:
        messages.error(request, "Serviço inválido.")
        return redirect("public_escolher_servico", slug=slug)

    try:
        data = datetime.fromisoformat(data_str).date()
    except Exception:
        messages.error(request, "Data inválida.")
        return redirect("public_escolher_servico", slug=slug)

    horarios = gerar_horarios_disponiveis(barbearia, servico, data)

    return render(
        request,
        "agenda/public_escolher_horario.html",
        {"barbearia": barbearia, "servico": servico, "data": data, "horarios": horarios},
    )


def public_confirmar_dados(request, slug):
    barbearia = get_object_or_404(BarberShop, slug=slug)

    servico_id = request.GET.get("servico")
    inicio_str = request.GET.get("inicio")

    try:
        servico = Service.objects.get(id=servico_id, barbearia=barbearia, ativo=True)
    except Service.DoesNotExist:
        messages.error(request, "Serviço inválido.")
        return redirect("public_escolher_servico", slug=slug)

    try:
        inicio_naive = datetime.fromisoformat(inicio_str)
        inicio = timezone.make_aware(inicio_naive, timezone.get_current_timezone()) if timezone.is_naive(inicio_naive) else inicio_naive
    except Exception:
        messages.error(request, "Horário inválido.")
        return redirect("public_escolher_servico", slug=slug)

    if request.method == "POST":
        form = PublicConfirmarDadosForm(request.POST)
        if form.is_valid():
            nome = form.cleaned_data["nome"]
            telefone = form.cleaned_data["telefone"]
            # Reusa cliente existente pelo telefone (ignorando máscara) ou cria um novo
            cliente = _get_or_create_client_by_phone(barbearia, nome, telefone)

            duracao = timedelta(minutes=servico.duracao_minutos or 30)
            fim = inicio + duracao

            agendamento = Appointment.objects.create(
                barbearia=barbearia,
                cliente=cliente,
                servico=servico,
                inicio=inicio,
                fim=fim,
                status="aguardando",
                criado_via="cliente_link",
                valor_no_momento=servico.preco,
            )

            # Se veio do Portal do Cliente em modo "remarcar", cancela o agendamento antigo
            old_id = request.session.pop("public_remarcar_antigo_id", None)
            old_cid = request.session.pop("public_remarcar_cliente_id", None)
            if old_id and old_cid and old_cid == cliente.id:
                Appointment.objects.filter(id=old_id, barbearia=barbearia, cliente=cliente).update(status="cancelado")

            request.session["ultimo_agendamento_id"] = agendamento.id

            # Se veio do Portal do Cliente (login por nome/telefone), volta pro painel.
            if request.session.get("public_cliente_id") == cliente.id and request.session.get(
                "public_cliente_slug"
            ) == barbearia.slug:
                try:
                    messages.success(request, "Agendamento atualizado com sucesso!")
                except Exception:
                    pass
                return redirect("public_cliente_painel", slug=barbearia.slug)

            return redirect("public_sucesso", slug=barbearia.slug)
    else:
        initial = {}
        if request.session.get("public_cliente_nome"):
            initial["nome"] = request.session.get("public_cliente_nome")
        if request.session.get("public_cliente_tel"):
            initial["telefone"] = request.session.get("public_cliente_tel")
        form = PublicConfirmarDadosForm(initial=initial)

    return render(
        request,
        "agenda/public_confirmar_dados.html",
        {"barbearia": barbearia, "servico": servico, "inicio": inicio, "form": form},
    )


def public_sucesso(request, slug):
    barbearia = get_object_or_404(BarberShop, slug=slug)

    agendamento_id = request.session.get("ultimo_agendamento_id")
    agendamento = None
    if agendamento_id:
        agendamento = (
            Appointment.objects.filter(id=agendamento_id, barbearia=barbearia)
            .select_related("servico", "cliente")
            .first()
        )

    wa_cliente_url = None
    wa_dono_url = None

    if agendamento:
        dt = timezone.localtime(agendamento.inicio)
        when = dt.strftime("%d/%m/%Y às %H:%M")
        serv_nome = agendamento.servico.nome if agendamento.servico else "Serviço"
        shop_nome = barbearia.nome or "Barbearia"

        msg_cliente = (
            f"✅ Agendamento confirmado!\n"
            f"📍 {shop_nome}\n"
            f"💈 {serv_nome}\n"
            f"🗓️ {when}\n"
            f"\n"
            f"Qualquer coisa é só chamar aqui 😄\n"
            f"\n🔁 Para cancelar ou remarcar depois, use o Portal do Cliente:\n"
            f"/agendar/{barbearia.slug}/cliente/\n"
        )

        msg_dono = (
            f"📌 Novo agendamento!\n"
            f"👤 Cliente: {agendamento.cliente.nome if agendamento.cliente else '—'}\n"
            f"📞 Tel: {agendamento.cliente.telefone if agendamento.cliente else '—'}\n"
            f"💈 Serviço: {serv_nome}\n"
            f"🗓️ {when}\n"
        )

        tel_cliente = _normalize_phone_to_wa(getattr(agendamento.cliente, "telefone", None))
        tel_dono = _normalize_phone_to_wa(getattr(barbearia, "telefone", None))

        if tel_cliente:
            wa_cliente_url = f"https://wa.me/{tel_cliente}?text=" + request.build_absolute_uri("/")[:-1]
            # We'll pass message via template using urlencode filter to avoid manual encoding

        if tel_dono:
            wa_dono_url = f"https://wa.me/{tel_dono}?text=" + request.build_absolute_uri("/")[:-1]

        # pass messages separately; template will urlencode them properly

    return render(
        request,
        "agenda/public_sucesso.html",
        {
            "barbearia": barbearia,
            "agendamento": agendamento,
            "wa_cliente": _normalize_phone_to_wa(getattr(agendamento.cliente, "telefone", None)) if agendamento else None,
            "wa_dono": _normalize_phone_to_wa(getattr(barbearia, "telefone", None)) if agendamento else None,
            "wa_msg_cliente": msg_cliente if agendamento else "",
            "wa_msg_dono": msg_dono if agendamento else "",
        },
    )


# ==========================
# HORÁRIOS (LOGADO)
# ==========================

@login_required
def horarios_view(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    dias_semana = [
        (0, "Segunda"),
        (1, "Terça"),
        (2, "Quarta"),
        (3, "Quinta"),
        (4, "Sexta"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    dias = []
    for num, nome in dias_semana:
        blocos = WorkDayConfig.objects.filter(barbearia=barbearia, dia_semana=num).order_by("inicio")
        dias.append({"num": num, "nome": nome, "qtd": blocos.count(), "blocos": blocos})

    return render(request, "agenda/horarios.html", {"barbearia": barbearia, "dias": dias})


@login_required
def novo_bloco_horario(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    if request.method == "POST":
        form = WorkDayConfigForm(request.POST)
        form.instance.barbearia = barbearia
        if form.is_valid():
            form.save()
            messages.success(request, "Bloco criado com sucesso.")
            return redirect("homemcom_horarios")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = WorkDayConfigForm(initial={"ativo": True})

    return render(
        request,
        "agenda/horarios_form.html",
        {"barbearia": barbearia, "form": form, "titulo": "Novo bloco"},
    )


@login_required
def editar_bloco_horario(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    bloco = get_object_or_404(WorkDayConfig, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = WorkDayConfigForm(request.POST, instance=bloco)
        form.instance.barbearia = barbearia
        if form.is_valid():
            form.save()
            messages.success(request, "Bloco atualizado com sucesso.")
            return redirect("homemcom_horarios")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = WorkDayConfigForm(instance=bloco)

    return render(
        request,
        "agenda/horarios_form.html",
        {"barbearia": barbearia, "form": form, "titulo": "Editar bloco"},
    )


@login_required
def excluir_bloco_horario(request, pk):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    bloco = get_object_or_404(WorkDayConfig, pk=pk, barbearia=barbearia)
    bloco.delete()
    messages.success(request, "Bloco excluído com sucesso.")
    return redirect("homemcom_horarios")


# ==========================
# SIGNUP / ONBOARDING (MULTI-TENANT)
# ==========================

from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.shortcuts import render, redirect

from .forms import SignupForm


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user, shop = form.save()

            login(request, user)
            messages.success(request, "Conta criada! Bora configurar sua loja rapidinho 😄")
            return redirect("onboarding_servicos", slug=shop.slug)

        messages.error(request, "Ops! Corrija os campos e tente novamente.")
    else:
        form = SignupForm()

    return render(request, "agenda/signup.html", {"form": form})

@login_required
def onboarding_servicos(request, slug):
    shop = get_shop_or_403(request, slug)
    if not shop:
        return HttpResponseForbidden("Sem permissão.")

    if Service.objects.filter(barbearia=shop).exists():
        return redirect("onboarding_horarios", slug=shop.slug)

    if request.method == "POST":
        form = ServiceForm(request.POST)
        if form.is_valid():
            s = form.save(commit=False)
            s.barbearia = shop
            s.save()
            messages.success(request, "Serviço adicionado! Pode adicionar mais ou avançar.")
            if "avancar" in request.POST:
                return redirect("onboarding_horarios", slug=shop.slug)
            return redirect("onboarding_servicos", slug=shop.slug)
    else:
        form = ServiceForm()

    return render(request, "agenda/onboarding_servicos.html", {"barbearia": shop, "form": form})


@login_required
def onboarding_horarios(request, slug):
    shop = get_shop_or_403(request, slug)
    if not shop:
        return HttpResponseForbidden("Sem permissão.")

    if request.method == "POST":
        form = WorkDayConfigForm(request.POST)
        if form.is_valid():
            h = form.save(commit=False)
            h.barbearia = shop
            h.save()
            messages.success(request, "Horário adicionado!")
            if "finalizar" in request.POST:
                return redirect("onboarding_finalizado", slug=shop.slug)
            return redirect("onboarding_horarios", slug=shop.slug)
    else:
        form = WorkDayConfigForm()

    horarios = WorkDayConfig.objects.filter(barbearia=shop, ativo=True).order_by("dia_semana", "inicio")
    return render(
        request,
        "agenda/onboarding_horarios.html",
        {"barbearia": shop, "form": form, "horarios": horarios},
    )


@login_required
def onboarding_finalizado(request, slug):
    shop = get_shop_or_403(request, slug)
    if not shop:
        return HttpResponseForbidden("Sem permissão.")

    link_publico = request.build_absolute_uri(f"/agendar/{shop.slug}/")
    return render(request, "agenda/onboarding_finalizado.html", {"barbearia": shop, "link_publico": link_publico})

# ==========================
# PLANOS (V1 / V2) — BLOCO 2
# ==========================
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from .models import PlanSubscription  # se seu model tiver outro nome me fala

@login_required
def homemcom_planos(request):
    """Tela premium de Planos: o cliente vê o plano atual e pode pedir troca / pagar quando quiser."""
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    from .models import PlanSubscription  # import local pra não quebrar nada do arquivo

    # garante assinatura
    sub, _ = PlanSubscription.objects.get_or_create(shop=barbearia)

    # preços (você pode trocar depois se quiser)
    PRECO_V1 = 39.90
    PRECO_V2 = 69.90

    if request.method == "POST":
        action = request.POST.get("action")
        target = request.POST.get("plan")

        if action == "choose" and target in (PlanSubscription.PLAN_V1, PlanSubscription.PLAN_V2):
            sub.requested_plan = target
            sub.save(update_fields=["requested_plan", "updated_at"])
            messages.success(request, f"Plano {target} selecionado. Agora é só pagar e eu libero pra você 😉")

            # manda pro pagamento pendente, se existir no seu projeto
            try:
                return redirect(reverse("homemcom_pagamento_pendente") + f"?plan={target}")
            except Exception:
                return redirect("homemcom_dashboard")

        if action == "pay_now":
            try:
                return redirect(reverse("homemcom_pagamento_pendente") + f"?plan={sub.requested_plan or sub.current_plan}")
            except Exception:
                return redirect("homemcom_dashboard")

    features_v1 = [
        "Link público de agendamento (cliente marca sozinho)",
        "Agenda do dia + visão semanal",
        "Serviços e horários de trabalho",
        "Cadastro de clientes e histórico",
        "Gestão financeira (serviços + produtos)",
    ]

    features_v2 = [
        "Tudo do V1",
        "Clientes fixos (bloqueio automático do horário)",
        "Pausas configuráveis (almoço/ausência)",
        "Confirmação de atendimento (concluído/no-show) antes de entrar no financeiro",
        "Cancelamento de agendamento pelo cliente via link seguro",
        "Dashboard financeiro avançado (versão 2)",
    ]

    context = {
        "barbearia": barbearia,
        "sub": sub,
        "preco_v1": f"{PRECO_V1:.2f}",
        "preco_v2": f"{PRECO_V2:.2f}",
        "features_v1": features_v1,
        "features_v2": features_v2,
    }
    return render(request, "agenda/homemcom_planos.html", context)

# agenda/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def planos(request):
    shop = _get_active_shop(request)
    if not shop:
        return redirect("homemcom_dashboard")

    sub, _ = PlanSubscription.objects.get_or_create(
        shop=shop,
        defaults={
            "current_plan": "V1",
            "status": "active",
            "next_due_date": timezone.localdate(),
        }
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "pay_now":
            plano = (sub.current_plan or "V1").upper().strip()
            if plano not in ("V1", "V2"):
                plano = "V1"
            return redirect(f"/pagamento-pendente/?plano={plano}")

        if action == "choose":
            plan = (request.POST.get("plan") or "V1").upper().strip()
            if plan not in ("V1", "V2"):
                plan = "V1"

            # ✅ aqui grava o pedido pra aparecer no admin
            sub.requested_plan = plan
            sub.status = "pending"
            sub.save(update_fields=["requested_plan", "status", "updated_at"])

            return redirect(f"/pagamento-pendente/?plano={plan}")

    context = {
        "sub": sub,
        "preco_v1": "39,90",
        "preco_v2": "69,90",
        "features_v1": [
            "Link público de agendamento (cliente marca sozinho)",
            "Agenda do dia + visão semanal",
            "Serviços e horários de trabalho",
            "Cadastro de clientes e histórico",
            "Gestão financeira (serviços + produtos)",
        ],
        "features_v2": [
            "Tudo do V1",
            "Clientes fixos (bloqueio automático de horário)",
            "Pausas configuráveis (almoço/ausência)",
            "Confirmação de atendimento (concluído/no-show) antes do financeiro",
            "Cancelamento pelo cliente via link seguro",
            "Dashboard financeiro avançado (versão 2)",
        ],
    }
    return render(request, "agenda/planos.html", context)


@login_required
def selecionar_plano(request, plano: str):
    """
    plano: "V1" ou "V2"
    Marca a escolha do cliente e manda pra tela de pagamento pendente já com o plano selecionado.
    """
    plano = (plano or "").upper().strip()
    if plano not in ("V1", "V2"):
        messages.error(request, "Plano inválido.")
        return redirect("planos")

    # Garante que existe registro de assinatura
    sub, _ = PlanSubscription.objects.get_or_create(user=request.user)

    sub.plano_atual = plano           # ou "plano" dependendo do seu model
    sub.plano_desejado = plano        # se existir no seu model; senão remove essa linha
    sub.save()

    # redireciona para pagamento pendente com o plano escolhido
    base = reverse("pagamento_pendente")
    query = urlencode({"plano": plano})
    return redirect(f"{base}?{query}")

@login_required
def pagamento_pendente(request):
    """
    Tela de pagamento manual (Pix + WhatsApp)
    """
    plano = (request.GET.get("plano") or "V1").upper().strip()
    if plano not in ("V1", "V2"):
        plano = "V1"

    valor = "39,90" if plano == "V1" else "69,90"

    # ====== SUAS INFOS REAIS ======
    pix_banco = "Pix (Nubank)"
    pix_beneficiario = "Lucas Castiglioni Toledo de Souza"
    pix_chave = "42506340866"  # CPF
    whatsapp_num = "5519981514883"  # 55 + DDD + número
    # ==============================

    msg = (
        f"Olá Lucas! Efetuei o pagamento do Kairós.app.\n\n"
        f"👤 Usuário: {request.user.username}\n"
        f"📦 Plano: {plano} (R$ {valor})\n"
        f"🧾 Envio o comprovante nesta mensagem.\n\n"
        f"Pode liberar meu acesso? 🙏"
    )

    whatsapp_link = f"https://wa.me/{whatsapp_num}?text={quote(msg)}"

    context = {
        "plano": plano,
        "valor_plano": valor,
        "pix_banco": pix_banco,
        "pix_beneficiario": pix_beneficiario,
        "pix_chave": pix_chave,
        "pix_chave_mask": pix_chave,  # se quiser mascarar depois, dá pra melhorar
        "whatsapp_link": whatsapp_link,
        "pix_qr_img": "img/pix_picpay_qr.png",  # ajuste se mudar o nome
    }

    return render(request, "agenda/pagamento_pendente.html", context)


# ==========================
# AGENDA INTELIGENTE (clientes fixos + pausas)
# ==========================
@login_required
def agenda_inteligente_view(request):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp

    if request.method == "POST":
        form = RecurringBlockForm(request.POST)
        if form.is_valid():
            kind = form.cleaned_data["kind"]
            titulo = form.cleaned_data["titulo"]
            dias = [int(d) for d in form.cleaned_data["dias"]]
            inicio = form.cleaned_data["inicio"]
            fim = form.cleaned_data["fim"]
            servico = form.cleaned_data.get("servico")
            duracao = form.cleaned_data.get("duracao_minutos")
            ativo = bool(form.cleaned_data.get("ativo", True))

            for d in dias:
                RecurringBlock.objects.create(
                    barbearia=barbearia,
                    kind=kind,
                    titulo=titulo,
                    dia_semana=d,
                    inicio=inicio,
                    fim=fim,
                    servico=servico,
                    duracao_minutos=duracao,
                    ativo=ativo,
                )

            messages.success(request, "Bloqueio criado! Agora esse horário não aparece mais pro público.")
            return redirect("homemcom_agenda_inteligente")
    else:
        form = RecurringBlockForm()

    blocks = RecurringBlock.objects.filter(barbearia=barbearia).order_by("dia_semana", "inicio")
    return render(request, "agenda/agenda_inteligente.html", {"barbearia": barbearia, "form": form, "blocks": blocks})


@login_required
def agenda_inteligente_toggle(request, pk: int):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp
    b = get_object_or_404(RecurringBlock, pk=pk, barbearia=barbearia)
    b.ativo = not b.ativo
    b.save(update_fields=["ativo"])
    return redirect("homemcom_agenda_inteligente")


@login_required
def agenda_inteligente_delete(request, pk: int):
    barbearia, resp = _require_shop(request)
    if resp:
        return resp
    b = get_object_or_404(RecurringBlock, pk=pk, barbearia=barbearia)
    b.delete()
    messages.success(request, "Bloqueio removido.")
    return redirect("homemcom_agenda_inteligente")

# ==========================
# PORTAL DO CLIENTE (PÚBLICO)
# Link estável: /agendar/<slug>/cliente/
# Cliente faz login com nome + telefone e vê/remarca/cancela agendamentos.
# ==========================

def _public_get_cliente(request, barbearia):
    cid = request.session.get("public_cliente_id")
    if not cid:
        return None
    return Client.objects.filter(id=cid, barbearia=barbearia).first()


def public_cliente_logout(request, slug):
    # logout simples do portal público
    request.session.pop("public_cliente_id", None)
    request.session.pop("public_cliente_nome", None)
    request.session.pop("public_cliente_tel", None)
    messages.success(request, "Você saiu do seu painel. Até parte do cabelo! ✂️😄")
    return redirect("public_cliente_login", slug=slug)


def public_cliente_login(request, slug):
    barbearia = get_object_or_404(BarberShop, slug=slug)

    # já logado? vai pro painel
    if _public_get_cliente(request, barbearia):
        return redirect("public_cliente_painel", slug=slug)

    if request.method == "POST":
        form = PublicClienteLoginForm(request.POST)
        if form.is_valid():
            nome = form.cleaned_data["nome"]
            telefone = form.cleaned_data["telefone"]

            # tenta achar o cliente por telefone; se não existir, cria
            # Obs: normalizamos telefone (somente dígitos). Mesmo assim, clientes antigos podem ter sido
            # salvos com máscara ("(19) 99999-9999"), então fazemos um fallback comparando dígitos.
            qs = (
                Client.objects.filter(barbearia=barbearia)
                .exclude(telefone__isnull=True)
                .exclude(telefone__exact="")
            )
            cliente = qs.filter(telefone=telefone).first()
            if not cliente:
                # fallback: compara apenas dígitos
                for c in qs.only("id", "telefone", "nome"):
                    digits = re.sub(r"\D+", "", c.telefone or "")
                    if len(digits) > 11 and digits.startswith("55"):
                        digits = digits[2:]
                    if digits == telefone:
                        cliente = c
                        break

            if not cliente:
                cliente = Client.objects.create(barbearia=barbearia, nome=nome, telefone=telefone)
            else:
                # atualiza nome caso esteja vazio
                if nome and (not cliente.nome):
                    cliente.nome = nome
                    cliente.save(update_fields=["nome"])

            request.session["public_cliente_id"] = cliente.id
            request.session["public_cliente_nome"] = cliente.nome
            request.session["public_cliente_tel"] = _digits_only(cliente.telefone)
            return redirect("public_cliente_painel", slug=slug)
    else:
        form = PublicClienteLoginForm(initial={
            "nome": request.session.get("public_cliente_nome", ""),
            "telefone": request.session.get("public_cliente_tel", ""),
        })

    return render(request, "agenda/public_cliente_login.html", {"barbearia": barbearia, "form": form})


def public_cliente_painel(request, slug):
    barbearia = get_object_or_404(BarberShop, slug=slug)

    cliente = _public_get_cliente(request, barbearia)
    if not cliente:
        return redirect("public_cliente_login", slug=slug)

    tel_digits = request.session.get("public_cliente_tel") or ""
    client_ids = _client_ids_by_phone(barbearia, tel_digits)

    now = timezone.localtime(timezone.now())

    base_qs = Appointment.objects.filter(
        barbearia=barbearia,
        cliente_id__in=client_ids,
    ).exclude(status="cancelado")

    # Mostra apenas agendamentos atuais (em andamento) e próximos.
    # Usamos fim__gte agora para incluir horários que já começaram e ainda não terminaram.
    agendamentos = base_qs.filter(fim__gte=now).order_by("inicio")

    ctx = {
        "barbearia": barbearia,
        "cliente": cliente,
        "agendamentos": agendamentos,
        "now": now,
    }
    return render(request, "agenda/public_cliente_painel.html", ctx)


def public_cliente_cancelar(request, slug, pk):
    barbearia = get_object_or_404(BarberShop, slug=slug)
    cliente = _public_get_cliente(request, barbearia)

    # pega TODOS os clientes com o mesmo telefone (evita duplicidade e garante que os agendamentos apareçam)
    tel_session = request.session.get("public_cliente_tel") or (cliente.telefone if cliente else "")
    cliente_ids = _client_ids_by_phone(barbearia, tel_session)
    if not cliente_ids and cliente:
        cliente_ids = [cliente.id]

    if not cliente:
        return redirect("public_cliente_login", slug=slug)

    # Segurança + robustez: o mesmo telefone pode ter gerado registros duplicados de Client.
    # No portal, a identidade do cliente é o TELEFONE, então a gente permite a ação
    # apenas se o agendamento estiver vinculado a QUALQUER Client com esse telefone.
    ag = get_object_or_404(Appointment, id=pk, barbearia=barbearia, cliente_id__in=cliente_ids)

    if request.method == "POST":
        # cancela
        ag.status = "cancelado"
        ag.save(update_fields=["status"])
        messages.success(request, "Prontinho! Agendamento cancelado ✅")
        return redirect("public_cliente_painel", slug=slug)

    return render(request, "agenda/public_cliente_cancelar.html", {"barbearia": barbearia, "cliente": cliente, "ag": ag})


def public_cliente_remarcar(request, slug, pk):
    barbearia = get_object_or_404(BarberShop, slug=slug)
    cliente = _public_get_cliente(request, barbearia)

    # pega TODOS os clientes com o mesmo telefone (evita duplicidade e garante que os agendamentos apareçam)
    tel_session = request.session.get("public_cliente_tel") or (cliente.telefone if cliente else "")
    cliente_ids = _client_ids_by_phone(barbearia, tel_session)
    if not cliente_ids and cliente:
        cliente_ids = [cliente.id]

    if not cliente:
        return redirect("public_cliente_login", slug=slug)

    # Mesma regra do cancelar: proteger contra clientes duplicados pelo mesmo telefone.
    ag = get_object_or_404(Appointment, id=pk, barbearia=barbearia, cliente_id__in=cliente_ids)

    # ✅ NOVO (e correto): remarcar usando o MESMO fluxo de horários disponíveis do agendamento público.
    # Isso evita sobrescrever horários já ocupados e respeita travas (horário mínimo, duração, etc.).
    request.session["public_remarcar_antigo_id"] = ag.id
    request.session["public_remarcar_cliente_id"] = ag.cliente_id
    request.session["public_servico_id"] = ag.servico_id

    # pré-preenche o formulário de confirmação com os dados do cliente do portal
    if tel_session:
        request.session["public_cliente_tel"] = tel_session
    if cliente and cliente.nome:
        request.session["public_cliente_nome"] = cliente.nome

    # Vai direto para a tela que lista horários LIVRES.
    return redirect("public_escolher_horario", slug=slug)

from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse


@login_required
def guia_sistema(request):
    """
    Guia interno (Premium) para o profissional aprender a usar o sistema
    e reduzir dúvidas de configuração.
    """
    # ✅ Seus dados
    suporte_whatsapp = "5519981514883"  # 55 + DDD + número (só dígitos)
    msg = (
        "Olá Lucas! Preciso de ajuda com o Kairós.app.\n\n"
        f"👤 Usuário: {request.user.username}\n"
        "📌 Assunto: (descreva aqui rapidinho)\n"
    )
    whatsapp_link = f"https://wa.me/{suporte_whatsapp}?text={quote(msg)}"

    # Link público (exemplo) — se você tem slug no context processor, substituímos depois
    # Por enquanto fica como texto explicativo no template.
    context = {
        "whatsapp_link": whatsapp_link,
        "suporte_whatsapp": suporte_whatsapp,
    }
    return render(request, "agenda/guia_sistema.html", context)
