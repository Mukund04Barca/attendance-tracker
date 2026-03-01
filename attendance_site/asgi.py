"""
ASGI config for attendance_site project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "attendance_site.settings")

application = get_asgi_application()

