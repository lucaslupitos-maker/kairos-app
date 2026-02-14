from __future__ import annotations

from django.shortcuts import redirect
from django.utils import timezone

from .models import PlanSubscription
from .views import _get_active_shop


class PaymentGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.open_prefixes = (
            "/admin",
            "/login",
            "/logout",
            "/static",
            "/planos",
            "/pagamento-pendente",
            "/agendar",
            "/accounts/login/",
            "/sair",
        )

    def __call__(self, request):
        path = request.path or "/"

        # rotas livres
        if any(path.startswith(p) for p in self.open_prefixes):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        shop = _get_active_shop(request)
        if not shop:
            return self.get_response(request)

        # ✅ bloqueia só o DONO (pra barbeiros/funcionários não ficar travando)
        if getattr(shop, "dono_id", None) and shop.dono_id != user.id and not user.is_superuser:
            return self.get_response(request)

        # se barbearia desativada -> bloqueia
        if getattr(shop, "ativo", True) is False:
            return redirect("pagamento_pendente")

        sub = PlanSubscription.objects.filter(shop=shop).first()
        if not sub:
            return self.get_response(request)

        # isento -> libera sempre
        if sub.is_exempt:
            return self.get_response(request)

        hoje = timezone.localdate()
        if (sub.next_due_date is None) or (sub.next_due_date < hoje):
            return redirect("pagamento_pendente")

        return self.get_response(request)