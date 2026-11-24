"""
Handing a task to an employee, and the employee's side of it.

Employees are not Zinvest users. When the founder assigns a task, the employee
gets a letter ("Dilshod gave you a task") with a link to the task's own page,
/task/<secret>. There they read it and answer: accepted, in progress, done,
with a note; the founder sees that on the task board. The secret is random,
lives only in the letter, and is stored as a SHA-256 hash. Sending the letter
again makes a new secret, so an old letter stops working.

A founder could type any address into an employee card, so letters are rate
limited per founder, and the employee can stop them from the task page.
"""
import hashlib
import json
import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt

from accounts import security
from accounts.mail import _deliver, pick_lang

from .models import Assignment, StartupProfile

log = logging.getLogger(__name__)

LETTERS_PER_HOUR = 30
NOTE_MAX = 1000
EMPLOYEE_STATUSES = (Assignment.Status.ACCEPTED, Assignment.Status.IN_PROGRESS, Assignment.Status.DONE)


def _hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def task_url(raw):
    return f"{settings.APP_ORIGIN}/task/{raw}"


def set_status(assignment, status):
    """One place that moves a task, so `done` and the timestamp never drift apart."""
    assignment.status = status
    assignment.done = status == Assignment.Status.DONE
    assignment.status_changed_at = timezone.now()


# --------------------------------------------------------------------------- #
# The letter
# --------------------------------------------------------------------------- #
LETTER = {
    "subject": {
        "ru": "{founder} поручил(а) вам задачу: {title}",
        "en": "{founder} gave you a task: {title}",
        "uz": "{founder} sizga topshiriq berdi: {title}",
    },
    "heading": {"ru": "Новая задача", "en": "A new task", "uz": "Yangi topshiriq"},
    "from": {
        "ru": "{founder} из «{business}» поручил(а) вам задачу в Zinvest.",
        "en": "{founder} from “{business}” gave you a task in Zinvest.",
        "uz": "«{business}» dan {founder} sizga Zinvest’da topshiriq berdi.",
    },
    "start": {"ru": "Начало", "en": "Starts", "uz": "Boshlanishi"},
    "deadline": {"ru": "Срок", "en": "Deadline", "uz": "Muddat"},
    "priority": {"ru": "Приоритет", "en": "Priority", "uz": "Muhimlik"},
    "priorities": {
        "low": {"ru": "Низкий", "en": "Low", "uz": "Past"},
        "normal": {"ru": "Обычный", "en": "Normal", "uz": "Oddiy"},
        "high": {"ru": "Срочно", "en": "Urgent", "uz": "Shoshilinch"},
    },
    "button": {"ru": "Открыть задачу", "en": "Open the task", "uz": "Topshiriqni ochish"},
    "how": {
        "ru": "По ссылке можно отметить, что вы приняли задачу, работаете над ней или уже сделали. Регистрироваться не нужно.",
        "en": "Use the link to mark the task accepted, in progress or done. No sign-up needed.",
        "uz": "Havola orqali topshiriqni qabul qilganingiz, ustida ishlayotganingiz yoki bajarganingizni belgilang. Ro‘yxatdan o‘tish shart emas.",
    },
    "why": {
        "ru": "Письмо пришло, потому что {founder} указал(а) этот адрес в карточке сотрудника. Если вы не знаете этого человека, просто удалите письмо; отключить такие письма можно на странице задачи.",
        "en": "You got this because {founder} entered this address on an employee card. If you do not know them, just delete it; you can turn these letters off on the task page.",
        "uz": "Bu xat {founder} ushbu manzilni xodim kartasiga kiritgani uchun keldi. Agar bu odamni tanimasangiz, xatni o‘chiring; bunday xatlarni topshiriq sahifasida o‘chirish mumkin.",
    },
}


def _date(value):
    return value.strftime("%d.%m.%Y") if value else ""


def _detail_rows(t, lang, a):
    rows = []
    if a.start_date:
        rows.append((t["start"][lang], _date(a.start_date)))
    if a.end_date:
        rows.append((t["deadline"][lang], _date(a.end_date)))
    rows.append((t["priority"][lang], t["priorities"][a.priority][lang]))
    return rows


def _letter_html(t, lang, founder, business, a, url):
    rows = _detail_rows(t, lang, a)
    detail = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;font-size:14px;white-space:nowrap">{escape(k)}</td>'
        f'<td style="padding:4px 0;font-size:14px;color:#0f172a;font-weight:600">{escape(v)}</td></tr>'
        for k, v in rows
    )
    description = (
        f'<tr><td style="font-size:15px;line-height:1.6;color:#334155;padding:0 0 16px;white-space:pre-wrap">{escape(a.description)}</td></tr>'
        if a.description else ""
    )
    urgent = ' <span style="display:inline-block;background:#fee2e2;color:#b91c1c;font-size:12px;font-weight:700;padding:2px 8px;border-radius:999px;vertical-align:middle">' \
        + escape(t["priorities"]["high"][lang]) + "</span>" if a.priority == Assignment.Priority.HIGH else ""
    origin = escape(settings.APP_ORIGIN)
    return f"""\
<!doctype html>
<html><body style="margin:0;padding:24px;background:#f4f4f7;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#0f172a">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:16px;padding:32px">
      <tr><td style="padding-bottom:16px"><img src="{origin}/email-logo.png" width="40" height="40" alt="" style="display:inline-block;vertical-align:middle;border:0"><span style="display:inline-block;vertical-align:middle;margin-left:10px;font-size:20px;font-weight:800;letter-spacing:-0.02em;color:#0A1128">Zinvest</span></td></tr>
      <tr><td style="font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#0052FF;padding-bottom:6px">{escape(t["heading"][lang])}</td></tr>
      <tr><td style="font-size:22px;font-weight:800;letter-spacing:-0.02em;line-height:1.3;padding-bottom:10px">{escape(a.title)}{urgent}</td></tr>
      <tr><td style="font-size:15px;line-height:1.6;color:#475569;padding-bottom:16px">{escape(t["from"][lang].format(founder=founder, business=business))}</td></tr>
      {description}
      <tr><td style="padding-bottom:20px"><table role="presentation" cellpadding="0" cellspacing="0">{detail}</table></td></tr>
      <tr><td style="padding-bottom:16px">
        <a href="{escape(url)}" style="display:inline-block;background:#0052FF;color:#ffffff;text-decoration:none;font-weight:700;font-size:15px;padding:12px 22px;border-radius:999px">{escape(t["button"][lang])}</a>
      </td></tr>
      <tr><td style="font-size:14px;line-height:1.6;color:#475569;padding-bottom:16px">{escape(t["how"][lang])}</td></tr>
      <tr><td style="font-size:12px;line-height:1.6;color:#94a3b8;word-break:break-all;padding-bottom:12px">{escape(url)}</td></tr>
      <tr><td style="font-size:12px;line-height:1.6;color:#94a3b8">{escape(t["why"][lang].format(founder=founder))}</td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def _names(founder_user):
    founder = " ".join(p for p in (founder_user.first_name, founder_user.last_name) if p).strip() or founder_user.email.split("@")[0]
    profile = StartupProfile.objects.filter(user=founder_user).only("name").first()
    business = (profile.name if profile and profile.name else "") or founder
    return founder, business


def send_letter(assignment, founder_user, lang):
    """
    Give the task a fresh link and mail it to the employee. Returns
    (sent, reason): reason is "no_email", "opted_out", "rate_limited" or "failed"
    when nothing went out.
    """
    employee = assignment.employee
    if not employee.email:
        return False, "no_email"
    if employee.email_opt_out:
        return False, "opted_out"
    if not security.hit("task-letter", founder_user.pk, LETTERS_PER_HOUR, 3600):
        return False, "rate_limited"
    raw = secrets.token_urlsafe(32)
    assignment.token_hash = _hash(raw)
    assignment.save(update_fields=["token_hash"])

    lang = pick_lang(lang)
    founder, business = _names(founder_user)
    t = LETTER
    url = task_url(raw)
    subject = t["subject"][lang].format(founder=founder, title=assignment.title)[:200]
    lines = [t["from"][lang].format(founder=founder, business=business), "", assignment.title]
    if assignment.description:
        lines += ["", assignment.description]
    lines += [""] + [f"{k}: {v}" for k, v in _detail_rows(t, lang, assignment)]
    lines += ["", f"{t['button'][lang]}: {url}",
              "", t["how"][lang], "", t["why"][lang].format(founder=founder)]
    sent = _deliver(subject, "\n".join(lines), _letter_html(t, lang, founder, business, assignment, url), employee.email, "task")
    if not sent:
        return False, "failed"
    assignment.notified_at = timezone.now()
    assignment.save(update_fields=["notified_at"])
    return True, ""


# --------------------------------------------------------------------------- #
# The employee's page: /api/startup/task/<secret>
# --------------------------------------------------------------------------- #
def _public_dict(a):
    founder, business = _names(a.employee.user)
    return {
        "title": a.title,
        "description": a.description,
        "priority": a.priority,
        "status": a.status,
        "start_date": a.start_date.isoformat() if a.start_date else None,
        "end_date": a.end_date.isoformat() if a.end_date else None,
        "note": a.assignee_note,
        "employee_name": a.employee.full_name,
        "founder_name": founder,
        "business_name": business,
        "letters_off": a.employee.email_opt_out,
    }


def _by_secret(raw):
    if not raw or len(raw) > 100:
        return None
    return (Assignment.objects.select_related("employee", "employee__user")
            .filter(token_hash=_hash(raw), employee__user__is_active=True).first())


@csrf_exempt
def task_page(request, secret):
    if request.method not in ("GET", "POST"):
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    ip = security.client_ip(request)
    if not security.hit("task-page", ip, 120, 600):
        return JsonResponse({"detail": "You are doing that too often. Please wait a little.", "code": "rate_limited"}, status=429)
    assignment = _by_secret(secret)
    if assignment is None:
        return JsonResponse({"detail": "This task link is no longer valid."}, status=404)
    if request.method == "GET":
        return JsonResponse({"task": _public_dict(assignment)})

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"detail": "Malformed JSON body."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"detail": "Expected an object."}, status=400)
    with transaction.atomic():
        a = Assignment.objects.select_for_update().select_related("employee").get(pk=assignment.pk)
        if "status" in data:
            if data["status"] not in EMPLOYEE_STATUSES:
                return JsonResponse({"detail": "Choose a valid status."}, status=400)
            set_status(a, data["status"])
        if "note" in data:
            a.assignee_note = str(data.get("note") or "").strip()[:NOTE_MAX]
        a.save()
        if data.get("letters_off") is True and not a.employee.email_opt_out:
            a.employee.email_opt_out = True
            a.employee.save(update_fields=["email_opt_out"])
    a.refresh_from_db()
    return JsonResponse({"task": _public_dict(a)})
