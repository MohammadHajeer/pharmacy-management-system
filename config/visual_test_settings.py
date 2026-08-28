from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / ".venv" / "login-visual-test.sqlite3",  # noqa: F405
    }
}


class LoginProbeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/accounts/login/" and request.method == "POST":
            from django.contrib.auth import get_user_model

            username = request.POST.get("username", "")
            password = request.POST.get("password", "")
            user = get_user_model().objects.filter(username=username).first()
            print(
                "LOGIN_PROBE",
                {
                    "username": username,
                    "password_length": len(password),
                    "password_matches": bool(user and user.check_password(password)),
                },
                flush=True,
            )
        return self.get_response(request)


MIDDLEWARE.insert(0, "config.visual_test_settings.LoginProbeMiddleware")  # noqa: F405
