from django.urls import path
from . import views

urlpatterns = [
    # Área do Marquinhos (interno)
    path('', views.dashboard, name='homemcom_dashboard'),
    path('novo-agendamento/', views.novo_agendamento, name='homemcom_novo_agendamento'),
    path('semana/', views.semana_view, name='homemcom_semana'),
    path('agenda-inteligente/', views.agenda_inteligente_view, name='homemcom_agenda_inteligente'),
    path('agenda-inteligente/<int:pk>/toggle/', views.agenda_inteligente_toggle, name='homemcom_agenda_inteligente_toggle'),
    path('agenda-inteligente/<int:pk>/excluir/', views.agenda_inteligente_delete, name='homemcom_agenda_inteligente_excluir'),

    path('configuracoes/', views.configuracoes_view, name='homemcom_configuracoes'),
    path('configuracoes/servico/novo/', views.novo_servico, name='homemcom_novo_servico'),
    path('configuracoes/servico/<int:pk>/', views.editar_servico, name='homemcom_editar_servico'),
    path('configuracoes/produto/novo/', views.novo_produto, name='homemcom_novo_produto'),
    path('configuracoes/produto/<int:pk>/', views.editar_produto, name='homemcom_editar_produto'),

    path('agendamento/<int:pk>/cancelar/', views.cancelar_agendamento, name='homemcom_cancelar_agendamento'),
    path('agendamento/<int:pk>/remarcar/', views.remarcar_agendamento, name='homemcom_remarcar_agendamento'),
    path('agendamento/<int:agendamento_id>/confirmar/', views.confirmar_agendamento, name='homemcom_confirmar_agendamento'),

    path('venda-produto/', views.registrar_venda_produto, name='homemcom_venda_produto'),

    path('horarios/', views.horarios_view, name='homemcom_horarios'),
    path('horarios/novo/', views.novo_bloco_horario, name='homemcom_horarios_novo'),
    path('horarios/<int:pk>/editar/', views.editar_bloco_horario, name='homemcom_horarios_editar'),
    path('horarios/<int:pk>/excluir/', views.excluir_bloco_horario, name='homemcom_horarios_excluir'),

    # Área pública (cliente)
    path("agendar/<slug:slug>/", views.public_escolher_servico, name="public_escolher_servico"),
    path("agendar/<slug:slug>/horarios/", views.public_escolher_horario, name="public_escolher_horario"),
    path("agendar/<slug:slug>/confirmar/", views.public_confirmar_dados, name="public_confirmar_dados"),
    path("agendar/<slug:slug>/sucesso/", views.public_sucesso, name="public_sucesso"),

    # Portal do Cliente (login + painel)
    path("agendar/<slug:slug>/cliente/", views.public_cliente_login, name="public_cliente_login"),
    path("agendar/<slug:slug>/cliente/painel/", views.public_cliente_painel, name="public_cliente_painel"),
    path("agendar/<slug:slug>/cliente/sair/", views.public_cliente_logout, name="public_cliente_logout"),
    path("agendar/<slug:slug>/cliente/cancelar/<int:pk>/", views.public_cliente_cancelar, name="public_cliente_cancelar"),
    path("agendar/<slug:slug>/cliente/remarcar/<int:pk>/", views.public_cliente_remarcar, name="public_cliente_remarcar"),
    path('relatorios/', views.relatorios_view, name='homemcom_relatorios'),
    path('planos/', views.homemcom_planos, name='homemcom_planos'),
    path("criar-conta/", views.signup, name="signup"),
    path("onboarding/<slug:slug>/servicos/", views.onboarding_servicos, name="onboarding_servicos"),
    path("onboarding/<slug:slug>/horarios/", views.onboarding_horarios, name="onboarding_horarios"),
    path("onboarding/<slug:slug>/finalizado/", views.onboarding_finalizado, name="onboarding_finalizado"),
    path("configuracoes/servico/<int:pk>/excluir/", views.excluir_servico, name="homemcom_excluir_servico"),
    path("configuracoes/produto/<int:pk>/excluir/", views.excluir_produto, name="homemcom_excluir_produto"),
    path("pagamento-pendente/", views.pagamento_pendente, name="pagamento_pendente"),
    path("planos/", views.planos, name="planos"),
    path("planos/selecionar/<str:plano>/", views.selecionar_plano, name="selecionar_plano"),
    path("guia/", views.guia_sistema, name="homemcom_guia_sistema"),
]