import os

if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    raise RuntimeError(
        "DJANGO_SETTINGS_MODULE environment variable is not set. "
        "Set it to 'sucuri_backend.settings.production' or 'sucuri_backend.settings.development'."
    )

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
