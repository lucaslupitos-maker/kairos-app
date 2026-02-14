from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('accounts/', include('django.contrib.auth.urls')),

    path('admin/', admin.site.urls),
    path('', include('agenda.urls')),  # homemcom agenda na raiz
    path("sair/", views.sair, name="sair"),
    path("pagamento-pendente/", views.pagamento_pendente, name="pagamento_pendente"),
]