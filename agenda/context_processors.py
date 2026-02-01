def current_account(request):
    if not request.user.is_authenticated:
        return {}

    barbearia = getattr(request, "barbearia", None)

    return {
        "current_user": request.user,
        "current_shop": barbearia,
    }