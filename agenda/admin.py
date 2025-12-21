from django.contrib import admin
from .models import (
    BarberShop,
    Service,
    Client,
    WorkDayConfig,
    Appointment,
    Cancellation,
    Product,
    ProductSale,
)


@admin.register(BarberShop)
class BarberShopAdmin(admin.ModelAdmin):
    list_display = ('nome', 'dono', 'telefone', 'slug')
    search_fields = ('nome', 'slug')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('nome', 'barbearia', 'preco', 'duracao_minutos', 'ativo')
    list_filter = ('barbearia', 'ativo')
    search_fields = ('nome',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nome', 'barbearia', 'telefone', 'bloqueado_online')
    list_filter = ('barbearia', 'bloqueado_online')
    search_fields = ('nome', 'telefone')


@admin.register(WorkDayConfig)
class WorkDayConfigAdmin(admin.ModelAdmin):
    list_display = ('barbearia', 'dia_semana', 'inicio', 'fim', 'ativo')
    list_filter = ('barbearia', 'dia_semana', 'ativo')


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'barbearia',
        'inicio',
        'cliente',
        'servico',
        'status',
        'valor_no_momento',
        'criado_via',
    )
    list_filter = ('barbearia', 'status', 'criado_via')
    search_fields = ('cliente__nome',)


@admin.register(Cancellation)
class CancellationAdmin(admin.ModelAdmin):
    list_display = ('agendamento', 'motivo', 'aprovado_por', 'criado_em')
    list_filter = ('motivo',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco', 'ativo', 'barbearia')
    list_filter = ('barbearia', 'ativo')
    search_fields = ('nome',)

@admin.register(ProductSale)
class ProductSaleAdmin(admin.ModelAdmin):
    list_display = ('produto', 'quantidade', 'valor_total', 'data_hora', 'barbearia')
    list_filter = ('barbearia', 'produto', 'data_hora')
    search_fields = ('produto__nome',)