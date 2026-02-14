from django.shortcuts import redirect
from django.utils import timezone

from .models import BarberShop


def _get_active_shop(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    # prioridade:
    # 1) isento_pagamento
    # 2) ativo e pago
    hoje = timezone.localdate()

    shop = (
        BarberShop.objects
        .filter(dono=user)
        .filter(
            isento_pagamento=True
        )
        .order_by("-id")
        .first()
    )

    if shop:
        return shop

    return (
        BarberShop.objects
        .filter(
            dono=user,
            ativo=True
        )
        .filter(
            pago_ate__gte=hoje
        )
        .order_by("-id")
        .first()
    )


def _require_shop(request):
    shop = _get_active_shop(request)
    if not shop:
        return None, redirect("signup")
    return shop, None