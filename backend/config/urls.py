from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from adminpanel import public
from config import cron
from files import views as files_views

urlpatterns = [
    path("api/auth/", include("accounts.urls")),
    path("api/ai/", include("ai_engine.urls")),
    path("api/learning/", include("learning.urls")),
    path("api/startup/", include("startup.urls")),
    path("api/copilot/", include("copilot.urls")),
    path("api/admin/", include("adminpanel.urls")),
    path("api/telegram/", include("telegrambot.urls")),
    path("api/announcements", public.announcements, name="announcements"),
    path("api/reports", public.report, name="reports"),
    path("api/cron/<str:job>", cron.run, name="cron"),
    path("api/", include("notes.urls")),
]

if settings.MEDIA_STORAGE == "db":
    # Uploads kept in the database (no disk on the host): Django serves them.
    urlpatterns += [path(f"{settings.MEDIA_URL.strip('/')}/<path:name>", files_views.serve, name="media")]
elif settings.DEBUG:
    # Dev only — in production Nginx serves /media/ straight off disk.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
