from django.urls import path
from . import views

urlpatterns = [
    # Área do Marquinhos (interno)
    path('', views.dashboard, name='homemcom_dashboard'),
    path('novo-agendamento/', views.novo_agendamento, name='homemcom_novo_agendamento'),
    path('semana/', views.semana_view, name='homemcom_semana'),

    path('configuracoes/', views.configuracoes_view, name='homemcom_configuracoes'),
    path('configuracoes/servico/novo/', views.novo_servico, name='homemcom_novo_servico'),
    path('configuracoes/servico/<int:pk>/', views.editar_servico, name='homemcom_editar_servico'),
    path('configuracoes/produto/novo/', views.novo_produto, name='homemcom_novo_produto'),
    path('configuracoes/produto/<int:pk>/', views.editar_produto, name='homemcom_editar_produto'),

    path('agendamento/<int:pk>/cancelar/', views.cancelar_agendamento, name='homemcom_cancelar_agendamento'),
    path('agendamento/<int:pk>/remarcar/', views.remarcar_agendamento, name='homemcom_remarcar_agendamento'),

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
    path('relatorios/', views.relatorios_view, name='homemcom_relatorios'),
    path("criar-conta/", views.signup, name="signup"),
    path("onboarding/<slug:slug>/servicos/", views.onboarding_servicos, name="onboarding_servicos"),
    path("onboarding/<slug:slug>/horarios/", views.onboarding_horarios, name="onboarding_horarios"),
    path("onboarding/<slug:slug>/finalizado/", views.onboarding_finalizado, name="onboarding_finalizado"),
    path("configuracoes/servico/<int:pk>/excluir/", views.excluir_servico, name="homemcom_excluir_servico"),
    path("configuracoes/produto/<int:pk>/excluir/", views.excluir_produto, name="homemcom_excluir_produto"),
]