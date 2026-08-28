from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.decorators.http import require_POST


def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("home")

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)

        return redirect("dashboard:home")

    return render(
        request,
        "accounts/login.html",
        {"form": form},
    )


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")
