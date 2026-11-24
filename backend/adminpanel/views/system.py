"""
The System page and the Startups list of the admin panel.

System: how this deployment is set up, as a checklist (DEBUG, keys, cookies,
two-factor, mail, Google, Gemini, the database and its migrations) plus who
can sign in how. Every value is a yes/no or a count, never a secret.

Startups: every founder's workspace and the market check from the intake.
"""
import platform
import sys
import time
from datetime import timedelta

import django
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.models import User
from startup.models import StartupProfile
from startup.research import VERDICTS, looks_empty

from ..models import PlatformSettings
from ..permissions import staff_required
from ..audit import audit
from .common import body, iso, method_not_allowed, paginate

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"


def _check(key, status, value=None):
    return {"key": key, "status": status, "value": value}


def _db():
    """Engine, one round trip's latency, and migrations not yet applied."""
    started = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    latency = round((time.perf_counter() - started) * 1000, 1)
    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return connection.vendor, latency, [f"{m.app_label}.{m.name}" for m, _ in pending]


def _staff_users():
    return User.objects.filter(is_active=True).filter(Q(is_superuser=True) | ~Q(staff_role=""))


@staff_required("system.view")
def system(request):
    if request.method != "GET":
        return method_not_allowed()
    vendor, latency, pending = _db()
    staff = _staff_users()
    staff_no_2fa = staff.filter(totp_enabled=False).count()
    mail_ready = "smtp" in settings.EMAIL_BACKEND and bool(settings.EMAIL_HOST and settings.EMAIL_HOST_USER)
    telegram_token = bool(getattr(settings, "TELEGRAM_BOT_TOKEN", ""))
    origin = settings.APP_ORIGIN

    checks = [
        # Security
        _check("debug_off", FAIL if settings.DEBUG else OK),
        _check("https_origin", OK if origin.startswith("https://") else (INFO if settings.DEBUG else FAIL), origin),
        _check("secure_cookies", OK if settings.REFRESH_COOKIE_SECURE else (INFO if settings.DEBUG else FAIL)),
        _check("allowed_hosts", FAIL if "*" in settings.ALLOWED_HOSTS else OK, len(settings.ALLOWED_HOSTS)),
        _check("admin_2fa_required", OK if settings.ADMIN_REQUIRE_2FA else (INFO if settings.DEBUG else FAIL)),
        _check("staff_2fa", WARN if staff_no_2fa else OK, staff_no_2fa),
        _check("superusers", WARN if User.objects.filter(is_superuser=True, is_active=True).exists() else OK,
               User.objects.filter(is_superuser=True, is_active=True).count()),
        _check("access_ttl", OK if settings.ACCESS_TOKEN_TTL <= timedelta(minutes=30) else WARN,
               int(settings.ACCESS_TOKEN_TTL.total_seconds() // 60)),
        _check("telegram_webhook_secret",
               INFO if not telegram_token else (OK if getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") else FAIL)),
        # Sign-in
        _check("mail", OK if mail_ready else WARN),
        _check("login_codes", OK if settings.LOGIN_EMAIL_CODE and mail_ready else (FAIL if settings.LOGIN_EMAIL_CODE else WARN)),
        _check("google", OK if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET else WARN),
        _check("registration", INFO, PlatformSettings.current().registration_open),
        # Services
        _check("gemini", OK if settings.GEMINI_API_KEY else FAIL),
        _check("database", OK if vendor == "postgresql" or settings.DEBUG else WARN, vendor),
        _check("db_latency", OK if latency < 50 else (WARN if latency < 250 else FAIL), latency),
        _check("migrations", FAIL if pending else OK, pending[:10]),
    ]

    users = User.objects.all()
    accounts = {
        "total": users.count(),
        "google_linked": users.exclude(google_sub="").count(),
        "passwordless": users.filter(password__startswith="!").count(),
        "email_verified": users.filter(email_verified_at__isnull=False).count(),
        "consented": users.filter(terms_accepted_at__isnull=False).count(),
        "staff": staff.count(),
        "staff_without_2fa": staff_no_2fa,
    }
    runtime = {
        "python": platform.python_version(),
        "django": django.get_version(),
        "region": _env("VERCEL_REGION"),
        "commit": _env("VERCEL_GIT_COMMIT_SHA")[:7],
        "deployment": _env("VERCEL_URL"),
        "platform": sys.platform,
        "server_time": iso(timezone.now()),
    }
    return JsonResponse({"checks": checks, "accounts": accounts, "runtime": runtime})


def _env(name):
    import os

    return os.environ.get(name, "")


# --------------------------------------------------------------------------- #
# Startups
# --------------------------------------------------------------------------- #
def _research(p):
    blocks = p.blocks if isinstance(p.blocks, dict) else {}
    research = blocks.get("research")
    return research if isinstance(research, dict) else None


def _answers(p):
    return p.onboarding if isinstance(p.onboarding, dict) else {}


def _review(p):
    review = (p.blocks or {}).get("review") if isinstance(p.blocks, dict) else None
    return review if isinstance(review, dict) else None


def _verdict(p, research, answers):
    """A person's review wins; then intakes saved before the junk check are shown for what they are."""
    review = _review(p)
    if review and review.get("verdict") in VERDICTS:
        return review["verdict"]
    if research and looks_empty(answers):
        return "insufficient"
    return research.get("verdict", "")


def _startup_row(p):
    research = _research(p) or {}
    answers = _answers(p)
    return {
        "id": str(p.id),
        "name": p.name or answers.get("name") or "",
        "owner": {"id": str(p.user_id), "email": p.user.email, "name": p.user.full_name},
        "location": answers.get("location", ""),
        "stage": answers.get("stage", ""),
        "market": answers.get("market", ""),
        "team": answers.get("team", ""),
        "verdict": _verdict(p, research, answers),
        "reviewed": bool(_review(p)),
        "searched": bool(research.get("searched")),
        "competitors": len(research.get("competitors") or []),
        "onboarded": p.onboarding_completed,
        "public": p.public_visible,
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
    }




@staff_required("startups.view")
def startups(request):
    if request.method != "GET":
        return method_not_allowed()
    qs = StartupProfile.objects.select_related("user").order_by("-updated_at")
    q = request.GET.get("q", "").strip()[:120]
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(user__email__icontains=q))
    verdict = request.GET.get("verdict", "")
    if verdict in VERDICTS:
        qs = qs.filter(blocks__research__verdict=verdict)
    elif verdict == "none":
        qs = qs.exclude(blocks__has_key="research")
    page = paginate(request, qs, _startup_row)
    all_profiles = StartupProfile.objects.all()
    counts = {v: all_profiles.filter(blocks__research__verdict=v).count() for v in VERDICTS}
    page["summary"] = {
        "total": all_profiles.count(),
        "onboarded": all_profiles.filter(onboarding_completed=True).count(),
        "checked": sum(counts.values()),
        "public": all_profiles.filter(public_visible=True).count(),
        "verdicts": counts,
        "week": all_profiles.filter(created_at__gte=timezone.now() - timedelta(days=7)).count(),
    }
    return JsonResponse(page)


@staff_required("startups.view")
def startup_detail(request, profile_id):
    if request.method != "GET":
        return method_not_allowed()
    p = get_object_or_404(StartupProfile.objects.select_related("user"), pk=profile_id)
    return JsonResponse(_startup_detail(p))


def _startup_detail(p):
    row = _startup_row(p)
    row["answers"] = _answers(p)
    row["research"] = _research(p)
    row["analysis"] = (p.blocks or {}).get("analysis", "") if isinstance(p.blocks, dict) else ""
    row["review"] = _review(p)
    row["counts"] = {
        "employees": p.user.startup_employees.count(),
        "products": p.user.startup_products.count(),
        "todos": p.user.startup_todos.count(),
    }
    return row


@staff_required("startups.review", write=True)
def startup_review(request, profile_id):
    """
    POST {verdict, note}: a person checked the project and sets the verdict
    (strong|promising|uncertain|weak|insufficient). The AI's own verdict is kept
    in review.ai_verdict. POST {clear: true} goes back to the AI's verdict.
    """
    if request.method != "POST":
        return method_not_allowed()
    p = get_object_or_404(StartupProfile.objects.select_related("user"), pk=profile_id)
    data, err = body(request)
    if err:
        return err
    blocks = p.blocks if isinstance(p.blocks, dict) else {}
    research = blocks.get("research") if isinstance(blocks.get("research"), dict) else None
    previous = _review(p) or {}
    ai_verdict = previous.get("ai_verdict", research.get("verdict", "") if research else "")

    if data.get("clear"):
        blocks.pop("review", None)
        if research is not None and ai_verdict in VERDICTS:
            research["verdict"] = ai_verdict
        action, summary = "startup.review_cleared", f"Back to the AI verdict for {p.name or p.pk}"
    else:
        verdict = data.get("verdict")
        if verdict not in VERDICTS:
            return JsonResponse({"detail": "Choose a valid verdict."}, status=400)
        blocks["review"] = {
            "verdict": verdict,
            "note": str(data.get("note") or "").strip()[:1000],
            "by": request.auth_user.email,
            "at": iso(timezone.now()),
            "ai_verdict": ai_verdict,
        }
        # The list's filter and counts read research.verdict: keep it in step.
        if research is not None:
            research["verdict"] = verdict
        action, summary = "startup.reviewed", f"Set {p.name or p.pk} to {verdict}"
    p.blocks = blocks
    p.save(update_fields=["blocks", "updated_at"])
    audit(request, action, target_type="startup", target_id=p.pk, summary=summary)
    return JsonResponse(_startup_detail(p))
