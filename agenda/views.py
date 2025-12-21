from datetime import datetime, timedelta, date

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Avg
from django.http import HttpResponse
from django.contrib import messages

from .models import (
    Appointment,
    BarberShop,
    WorkDayConfig,
    Client,
    Service,
    Product,
    ProductSale,
)
from .forms import (
    NovoAgendamentoForm,
    CancelamentoForm,
    RemarcarAgendamentoForm,
    PublicEscolherServicoForm,
    PublicConfirmarDadosForm,
    ServiceForm,
    ProductForm,
    ProductSaleForm,
    WorkDayConfigForm,
)


# ==========================
# DASHBOARD (MARQUINHOS)
# ==========================

def dashboard(request):
    barbearia = BarberShop.objects.first()
    hoje = timezone.localdate()

    if not barbearia:
        messages.error(request, "Nenhuma barbearia cadastrada. Cadastre primeiro no admin.")
        return render(request, 'agenda/homemcom_dashboard.html', {
            'data_hoje': hoje,
            'agendamentos_hoje': [],
            'total_atendimentos_hoje': 0,
            'total_valor_hoje': f'{0:.2f}',
            'ticket_medio_hoje': f'{0:.2f}',
            'total_valor_semana': f'{0:.2f}',
            'total_valor_mes': f'{0:.2f}',
            'total_cancelado_hoje': f'{0:.2f}',
            'total_servicos_hoje': f'{0:.2f}',
            'total_produtos_hoje': f'{0:.2f}',
            'total_servicos_semana': f'{0:.2f}',
            'total_produtos_semana': f'{0:.2f}',
            'total_servicos_mes': f'{0:.2f}',
            'total_produtos_mes': f'{0:.2f}',
        })

    # Agendamentos do dia
    agendamentos_hoje = Appointment.objects.filter(
        barbearia=barbearia,
        inicio__date=hoje
    ).select_related('cliente', 'servico')

    confirmados = agendamentos_hoje.filter(status='confirmado')

    # SERVIÇOS (DIA)
    total_atendimentos_hoje = confirmados.count()
    total_servicos_hoje = confirmados.aggregate(
        total=Sum('valor_no_momento')
    )['total'] or 0

    ticket_medio_hoje = (
        confirmados.aggregate(media=Avg('valor_no_momento'))['media'] or 0
    )

    # PRODUTOS (DIA)
    vendas_produtos_hoje = ProductSale.objects.filter(
        barbearia=barbearia,
        data_hora__date=hoje,
    )
    total_produtos_hoje = vendas_produtos_hoje.aggregate(
        total=Sum('valor_total')
    )['total'] or 0

    # TOTAL GERAL DO DIA
    total_valor_hoje = total_servicos_hoje + total_produtos_hoje

    # SEMANA
    inicio_semana = hoje - timedelta(days=hoje.weekday())  # segunda
    fim_semana = inicio_semana + timedelta(days=6)         # domingo

    confirmados_semana = Appointment.objects.filter(
        barbearia=barbearia,
        status='confirmado',
        inicio__date__gte=inicio_semana,
        inicio__date__lte=fim_semana,
    )
    total_servicos_semana = confirmados_semana.aggregate(
        total=Sum('valor_no_momento')
    )['total'] or 0

    vendas_produtos_semana = ProductSale.objects.filter(
        barbearia=barbearia,
        data_hora__date__gte=inicio_semana,
        data_hora__date__lte=fim_semana,
    )
    total_produtos_semana = vendas_produtos_semana.aggregate(
        total=Sum('valor_total')
    )['total'] or 0

    total_valor_semana = total_servicos_semana + total_produtos_semana

    # MÊS
    confirmados_mes = Appointment.objects.filter(
        barbearia=barbearia,
        status='confirmado',
        inicio__year=hoje.year,
        inicio__month=hoje.month,
    )
    total_servicos_mes = confirmados_mes.aggregate(
        total=Sum('valor_no_momento')
    )['total'] or 0

    vendas_produtos_mes = ProductSale.objects.filter(
        barbearia=barbearia,
        data_hora__year=hoje.year,
        data_hora__month=hoje.month,
    )
    total_produtos_mes = vendas_produtos_mes.aggregate(
        total=Sum('valor_total')
    )['total'] or 0

    total_valor_mes = total_servicos_mes + total_produtos_mes

    # CANCELADOS DO DIA (só serviços)
    cancelados_hoje = Appointment.objects.filter(
        barbearia=barbearia,
        status='cancelado',
        inicio__date=hoje
    )
    total_cancelado_hoje = cancelados_hoje.aggregate(
        total=Sum('valor_no_momento')
    )['total'] or 0

    context = {
        'data_hoje': hoje,
        'agendamentos_hoje': agendamentos_hoje,
        'total_atendimentos_hoje': total_atendimentos_hoje,
        'total_valor_hoje': f'{total_valor_hoje:.2f}',
        'ticket_medio_hoje': f'{ticket_medio_hoje:.2f}',

        'total_valor_semana': f'{total_valor_semana:.2f}',
        'total_valor_mes': f'{total_valor_mes:.2f}',
        'total_cancelado_hoje': f'{total_cancelado_hoje:.2f}',

        'total_servicos_hoje': f'{total_servicos_hoje:.2f}',
        'total_produtos_hoje': f'{total_produtos_hoje:.2f}',
        'total_servicos_semana': f'{total_servicos_semana:.2f}',
        'total_produtos_semana': f'{total_produtos_semana:.2f}',
        'total_servicos_mes': f'{total_servicos_mes:.2f}',
        'total_produtos_mes': f'{total_produtos_mes:.2f}',
    }
    return render(request, 'agenda/homemcom_dashboard.html', context)


def novo_agendamento(request):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        messages.error(request, "Nenhuma barbearia cadastrada. Cadastre primeiro no admin.")
        return redirect('homemcom_dashboard')

    if request.method == "POST":
        form = NovoAgendamentoForm(request.POST, barbearia=barbearia)
        if form.is_valid():
            form.save(barbearia=barbearia)
            messages.success(request, "Agendamento criado com sucesso!")
            return redirect('homemcom_dashboard')
    else:
        agora = timezone.localtime()
        form = NovoAgendamentoForm(
            barbearia=barbearia,
            initial={'inicio': agora.replace(second=0, microsecond=0)}
        )

    context = {
        'form': form,
        'barbearia': barbearia,
    }
    return render(request, 'agenda/novo_agendamento.html', context)

def relatorios_view(request):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        messages.error(request, "Nenhuma barbearia cadastrada.")
        return redirect('homemcom_dashboard')

    hoje = timezone.localdate()

    # --- Padrão: mês atual ---
    inicio_padrao = hoje.replace(day=1)
    # próximo mês (truque seguro)
    if hoje.month == 12:
        prox_mes = date(hoje.year + 1, 1, 1)
    else:
        prox_mes = date(hoje.year, hoje.month + 1, 1)
    fim_padrao = prox_mes - timedelta(days=1)

    # --- Lê período do GET (form) ---
    inicio_str = request.GET.get("inicio")
    fim_str = request.GET.get("fim")

    def parse_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    data_inicio = parse_date(inicio_str) or inicio_padrao
    data_fim = parse_date(fim_str) or fim_padrao

    # Garantia: se inverter, a gente troca
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    # --- SERVIÇOS (appointments confirmados) ---
    qs_servicos = Appointment.objects.filter(
        barbearia=barbearia,
        status='confirmado',
        inicio__date__gte=data_inicio,
        inicio__date__lte=data_fim,
    )

    total_servicos = qs_servicos.aggregate(total=Sum('valor_no_momento'))['total'] or 0
    qtd_servicos = qs_servicos.count()
    ticket_medio = qs_servicos.aggregate(media=Avg('valor_no_momento'))['media'] or 0

    # Cancelados (só serviços)
    total_cancelado = Appointment.objects.filter(
        barbearia=barbearia,
        status='cancelado',
        inicio__date__gte=data_inicio,
        inicio__date__lte=data_fim,
    ).aggregate(total=Sum('valor_no_momento'))['total'] or 0

    # --- PRODUTOS (vendas) ---
    qs_produtos = ProductSale.objects.filter(
        barbearia=barbearia,
        data_hora__date__gte=data_inicio,
        data_hora__date__lte=data_fim,
    )

    total_produtos = qs_produtos.aggregate(total=Sum('valor_total'))['total'] or 0
    qtd_itens_produtos = qs_produtos.aggregate(total=Sum('quantidade'))['total'] or 0

    # --- TOTAL GERAL ---
    total_geral = total_servicos + total_produtos

    context = {
        'barbearia': barbearia,
        'hoje': hoje,
        'data_inicio': data_inicio,
        'data_fim': data_fim,

        'total_servicos': f'{total_servicos:.2f}',
        'qtd_servicos': qtd_servicos,
        'ticket_medio': f'{ticket_medio:.2f}',

        'total_produtos': f'{total_produtos:.2f}',
        'qtd_itens_produtos': qtd_itens_produtos,

        'total_cancelado': f'{total_cancelado:.2f}',
        'total_geral': f'{total_geral:.2f}',
    }
    return render(request, 'agenda/relatorios.html', context)



def cancelar_agendamento(request, pk):
    barbearia = BarberShop.objects.first()
    agendamento = get_object_or_404(Appointment, pk=pk, barbearia=barbearia)

    if agendamento.status == 'cancelado':
        messages.info(request, "Este agendamento já está cancelado.")
        return redirect('homemcom_dashboard')

    if request.method == "POST":
        form = CancelamentoForm(request.POST)
        if form.is_valid():
            cancelamento = form.save(commit=False)
            cancelamento.agendamento = agendamento
            cancelamento.aprovado_por = request.user if request.user.is_authenticated else None
            cancelamento.save()

            agendamento.status = 'cancelado'
            agendamento.save()

            messages.success(request, "Agendamento cancelado com sucesso.")
            return redirect('homemcom_dashboard')
    else:
        form = CancelamentoForm()

    context = {
        'form': form,
        'agendamento': agendamento,
        'barbearia': barbearia,
    }
    return render(request, 'agenda/cancelar_agendamento.html', context)


def remarcar_agendamento(request, pk):
    barbearia = BarberShop.objects.first()
    agendamento = get_object_or_404(Appointment, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = RemarcarAgendamentoForm(request.POST, instance=agendamento)
        if form.is_valid():
            form.save()
            messages.success(request, "Agendamento remarcado com sucesso.")
            return redirect('homemcom_dashboard')
    else:
        form = RemarcarAgendamentoForm(
            instance=agendamento,
            initial={'inicio': agendamento.inicio}
        )

    context = {
        'form': form,
        'agendamento': agendamento,
        'barbearia': barbearia,
    }
    return render(request, 'agenda/remarcar_agendamento.html', context)


# ==========================
# VISÃO SEMANAL
# ==========================

def semana_view(request):
    """
    Visão semanal: mostra todos os agendamentos da semana (segunda a domingo),
    com navegação para semanas passada e futura.
    """
    barbearia = BarberShop.objects.first()
    if not barbearia:
        return HttpResponse("Barbearia não configurada.")

    hoje = timezone.localdate()

    # data de referência vinda da URL ?ref=YYYY-MM-DD
    ref_str = request.GET.get("ref")
    if ref_str:
        try:
            ref_date = datetime.fromisoformat(ref_str).date()
        except ValueError:
            ref_date = hoje
    else:
        ref_date = hoje

    # segunda e domingo da semana da data de referência
    inicio_semana = ref_date - timedelta(days=ref_date.weekday())  # segunda
    fim_semana = inicio_semana + timedelta(days=6)                 # domingo

    # datas de referência para navegação
    prev_ref = inicio_semana - timedelta(days=7)
    next_ref = inicio_semana + timedelta(days=7)

    dias_semana = []
    for i in range(7):
        data = inicio_semana + timedelta(days=i)
        agendamentos = (
            Appointment.objects
            .filter(barbearia=barbearia, inicio__date=data)
            .select_related('cliente', 'servico')
            .order_by('inicio')
        )

        total_dia = (
            agendamentos
            .filter(status='confirmado')
            .aggregate(total=Sum('valor_no_momento'))
        )['total'] or 0

        dias_semana.append({
            'data': data,
            'agendamentos': agendamentos,
            'total_dia': total_dia,
        })

    context = {
        'barbearia': barbearia,
        'hoje': hoje,
        'inicio_semana': inicio_semana,
        'fim_semana': fim_semana,
        'dias_semana': dias_semana,
        'prev_ref': prev_ref,
        'next_ref': next_ref,
        'ref_date': ref_date,
    }
    return render(request, 'agenda/semana.html', context)


# ==========================
# CONFIGURAÇÕES (SERVIÇOS / PRODUTOS / HORÁRIOS)
# ==========================

def configuracoes_view(request):
    """
    Tela de configurações: lista serviços, produtos e horários.
    Permite acessar edição rápida de serviços/produtos.
    """
    barbearia = BarberShop.objects.first()
    if not barbearia:
        return HttpResponse("Barbearia não configurada.")

    servicos = Service.objects.filter(barbearia=barbearia).order_by('nome')
    produtos = Product.objects.filter(barbearia=barbearia).order_by('nome')
    horarios = WorkDayConfig.objects.filter(barbearia=barbearia, ativo=True).order_by('dia_semana', 'inicio')

    context = {
        'barbearia': barbearia,
        'servicos': servicos,
        'produtos': produtos,
        'horarios': horarios,
    }
    return render(request, 'agenda/configuracoes.html', context)


def novo_servico(request):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        return HttpResponse("Barbearia não configurada.")

    if request.method == "POST":
        form = ServiceForm(request.POST)
        if form.is_valid():
            servico = form.save(commit=False)
            servico.barbearia = barbearia
            servico.save()
            messages.success(request, "Serviço criado com sucesso.")
            return redirect('homemcom_configuracoes')
    else:
        form = ServiceForm()

    return render(request, 'agenda/editar_servico.html', {
        'form': form,
        'barbearia': barbearia,
        'titulo': 'Novo serviço',
    })


def editar_servico(request, pk):
    barbearia = BarberShop.objects.first()
    servico = get_object_or_404(Service, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = ServiceForm(request.POST, instance=servico)
        if form.is_valid():
            form.save()
            messages.success(request, "Serviço atualizado com sucesso.")
            return redirect('homemcom_configuracoes')
    else:
        form = ServiceForm(instance=servico)

    return render(request, 'agenda/editar_servico.html', {
        'form': form,
        'barbearia': barbearia,
        'titulo': f'Editar serviço: {servico.nome}',
    })


def novo_produto(request):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        return HttpResponse("Barbearia não configurada.")

    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            produto = form.save(commit=False)
            produto.barbearia = barbearia
            produto.save()
            messages.success(request, "Produto criado com sucesso.")
            return redirect('homemcom_configuracoes')
    else:
        form = ProductForm()

    return render(request, 'agenda/editar_produto.html', {
        'form': form,
        'barbearia': barbearia,
        'titulo': 'Novo produto',
    })


def editar_produto(request, pk):
    barbearia = BarberShop.objects.first()
    produto = get_object_or_404(Product, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=produto)
        if form.is_valid():
            form.save()
            messages.success(request, "Produto atualizado com sucesso.")
            return redirect('homemcom_configuracoes')
    else:
        form = ProductForm(instance=produto)

    return render(request, 'agenda/editar_produto.html', {
        'form': form,
        'barbearia': barbearia,
        'titulo': f'Editar produto: {produto.nome}',
    })


# ==========================
# REGISTRAR VENDA DE PRODUTO
# ==========================

def registrar_venda_produto(request):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        return HttpResponse("Barbearia não configurada.")

    if request.method == "POST":
        form = ProductSaleForm(request.POST, barbearia=barbearia)
        if form.is_valid():
            form.save(barbearia=barbearia)
            messages.success(request, "Venda registrada com sucesso.")
            return redirect('homemcom_dashboard')
    else:
        form = ProductSaleForm(barbearia=barbearia)

    return render(request, 'agenda/registrar_venda_produto.html', {
        'form': form,
        'barbearia': barbearia,
    })


# ==========================
# LÓGICA DE HORÁRIOS LIVRES
# ==========================

def gerar_horarios_disponiveis(barbearia, servico, data):
    """
    Gera horários livres considerando vários blocos no mesmo dia.
    """
    configs = WorkDayConfig.objects.filter(
        barbearia=barbearia,
        dia_semana=data.weekday(),
        ativo=True
    ).order_by('inicio')

    if not configs.exists():
        return []

    tz = timezone.get_current_timezone()
    duracao = timedelta(minutes=servico.duracao_minutos or 30)

    agendamentos = Appointment.objects.filter(
        barbearia=barbearia,
        inicio__date=data
    ).exclude(status='cancelado')

    horarios_livres = []

    for config in configs:
        inicio_bloco = timezone.make_aware(datetime.combine(data, config.inicio), tz)
        fim_bloco = timezone.make_aware(datetime.combine(data, config.fim), tz)

        inicio = inicio_bloco
        while inicio + duracao <= fim_bloco:
            fim = inicio + duracao

            conflito = agendamentos.filter(
                inicio__lt=fim,
                fim__gt=inicio
            ).exists()

            if not conflito:
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
            servico = form.cleaned_data['servico']
            data = form.cleaned_data['data']
            return redirect(
                f"/agendar/{slug}/horarios/?servico={servico.id}&data={data.isoformat()}"
            )
    else:
        hoje = timezone.localdate()
        form = PublicEscolherServicoForm(
            barbearia=barbearia,
            initial={'data': hoje}
        )

    return render(request, 'agenda/public_escolher_servico.html', {
        'form': form,
        'barbearia': barbearia,
    })


def public_escolher_horario(request, slug):
    """
    2º passo: mostrar horários disponíveis para o serviço e dia escolhidos.
    """
    barbearia = get_object_or_404(BarberShop, slug=slug)
    if not barbearia:
        return HttpResponse("Barbearia não configurada.")

    servico_id = request.GET.get('servico')
    data_str = request.GET.get('data')

    try:
        servico = Service.objects.get(id=servico_id, barbearia=barbearia, ativo=True)
    except Service.DoesNotExist:
        messages.error(request, "Serviço inválido.")
        return redirect('public_escolher_servico')

    try:
        data = datetime.fromisoformat(data_str).date()
    except Exception:
        messages.error(request, "Data inválida.")
        return redirect('public_escolher_servico')

    horarios = gerar_horarios_disponiveis(barbearia, servico, data)

    context = {
        'barbearia': barbearia,
        'servico': servico,
        'data': data,
        'horarios': horarios,
    }
    return render(request, 'agenda/public_escolher_horario.html', context)


def public_confirmar_dados(request, slug):
    """
    3º passo: cliente informa nome/telefone e confirmamos o agendamento.
    """
    barbearia = get_object_or_404(BarberShop, slug=slug)
    if not barbearia:
        return HttpResponse("Barbearia não configurada.")

    servico_id = request.GET.get('servico')
    inicio_str = request.GET.get('inicio')

    try:
        servico = Service.objects.get(id=servico_id, barbearia=barbearia, ativo=True)
    except Service.DoesNotExist:
        messages.error(request, "Serviço inválido.")
        return redirect('public_escolher_servico')

    try:
        inicio_naive = datetime.fromisoformat(inicio_str)
        inicio = timezone.make_aware(inicio_naive, timezone.get_current_timezone()) \
            if timezone.is_naive(inicio_naive) else inicio_naive
    except Exception:
        messages.error(request, "Horário inválido.")
        return redirect('public_escolher_servico')

    if request.method == "POST":
        form = PublicConfirmarDadosForm(request.POST)
        if form.is_valid():
            nome = form.cleaned_data['nome']
            telefone = form.cleaned_data['telefone']

            if telefone:
                cliente, _ = Client.objects.get_or_create(
                    barbearia=barbearia,
                    telefone=telefone,
                    defaults={'nome': nome}
                )
                if cliente.nome != nome and cliente.nome:
                    # poderia atualizar o nome, se quiser
                    pass
            else:
                cliente = Client.objects.create(
                    barbearia=barbearia,
                    nome=nome
                )

            duracao = timedelta(minutes=servico.duracao_minutos or 30)
            fim = inicio + duracao

            agendamento = Appointment.objects.create(
                barbearia=barbearia,
                cliente=cliente,
                servico=servico,
                inicio=inicio,
                fim=fim,
                status='confirmado',
                criado_via='cliente_link',
                valor_no_momento=servico.preco,
            )

            request.session['ultimo_agendamento_id'] = agendamento.id
            return redirect('public_sucesso', slug=barbearia.slug)
    else:
        form = PublicConfirmarDadosForm()

    context = {
        'barbearia': barbearia,
        'servico': servico,
        'inicio': inicio,
        'form': form,
    }
    return render(request, 'agenda/public_confirmar_dados.html', context)


def public_sucesso(request, slug):
    barbearia = get_object_or_404(BarberShop, slug=slug)

    agendamento_id = request.session.get('ultimo_agendamento_id')
    agendamento = None
    if agendamento_id:
        agendamento = Appointment.objects.filter(id=agendamento_id, barbearia=barbearia).select_related('servico', 'cliente').first()

    return render(request, 'agenda/public_sucesso.html', {
        'barbearia': barbearia,
        'agendamento': agendamento,
    })

def horarios_view(request):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        messages.error(request, "Nenhuma barbearia cadastrada.")
        return redirect("homemcom_dashboard")

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
        blocos = (WorkDayConfig.objects
                  .filter(barbearia=barbearia, dia_semana=num)
                  .order_by("inicio"))
        dias.append({
            "num": num,
            "nome": nome,
            "qtd": blocos.count(),
            "blocos": blocos,
        })

    return render(request, "agenda/horarios.html", {
        "barbearia": barbearia,
        "dias": dias,
    })


def novo_bloco_horario(request):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        messages.error(request, "Nenhuma barbearia cadastrada.")
        return redirect("homemcom_dashboard")

    if request.method == "POST":
        form = WorkDayConfigForm(request.POST)

        # ✅ AQUI É O PULO DO GATO:
        form.instance.barbearia = barbearia

        if form.is_valid():
            form.save()
            messages.success(request, "Bloco criado com sucesso.")
            return redirect("homemcom_horarios")
        else:
            messages.error(request, "Corrija os campos destacados.")
    else:
        form = WorkDayConfigForm(initial={"ativo": True})

    return render(request, "agenda/horarios_form.html", {
        "barbearia": barbearia,
        "form": form,
        "titulo": "Novo bloco",
    })

def editar_bloco_horario(request, pk):
    barbearia = BarberShop.objects.first()
    if not barbearia:
        messages.error(request, "Nenhuma barbearia cadastrada.")
        return redirect("homemcom_dashboard")

    bloco = get_object_or_404(WorkDayConfig, pk=pk, barbearia=barbearia)

    if request.method == "POST":
        form = WorkDayConfigForm(request.POST, instance=bloco)
        form.instance.barbearia = barbearia
        if form.is_valid():
            form.save()
            messages.success(request, "Bloco atualizado com sucesso.")
            return redirect("homemcom_horarios")
        else:
            messages.error(request, "Corrija os campos destacados.")
    else:
        form = WorkDayConfigForm(instance=bloco)

    return render(request, "agenda/horarios_form.html", {
        "barbearia": barbearia,
        "form": form,
        "titulo": "Editar bloco",
    })


def excluir_bloco_horario(request, pk):
    barbearia = BarberShop.objects.first()
    bloco = get_object_or_404(WorkDayConfig, pk=pk, barbearia=barbearia)

    bloco.delete()
    messages.success(request, "Bloco excluído com sucesso.")
    return redirect("homemcom_horarios")