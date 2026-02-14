from django.contrib.auth import logout
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

@require_POST
def sair(request):
    logout(request)
    return redirect("login")  # ou sua home


@require_POST
def pagamento_pendente(request):
    return render(request, "agenda/pagamento_pendente.html")