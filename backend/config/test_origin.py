"""Cross-site requests (config/origin.py) and the production start-up checks (settings)."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.jwt_utils import encode_access_token
from accounts.models import User
from learning.models import Lesson, Unit

BACKEND = Path(__file__).resolve().parents[1]


class CrossSiteRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(email="victim@example.test", password="Str0ng-Passphrase!")

    def login(self, **headers):
        return self.client.post("/api/auth/login", data=json.dumps({"email": "victim@example.test", "password": "Str0ng-Passphrase!"}),
                                content_type="application/json", **headers)

    def test_a_forged_sign_in_from_another_site_is_refused(self):
        response = self.login(HTTP_ORIGIN="https://evil.example")
        self.assertEqual((response.status_code, response.json()["code"]), (403, "cross_site"))
        self.assertNotIn("refresh_token", response.cookies)

    def test_the_app_itself_and_non_browser_callers_pass(self):
        self.assertEqual(self.login(HTTP_ORIGIN="http://testserver").status_code, 200)
        self.assertEqual(self.login().status_code, 200)  # no Origin: curl, Telegram, cron

    @override_settings(CSRF_TRUSTED_ORIGINS=["https://zinvest.uz"])
    def test_a_trusted_origin_passes(self):
        self.assertEqual(self.login(HTTP_ORIGIN="https://zinvest.uz").status_code, 200)

    def test_null_origins_and_cross_site_fetches_are_refused(self):
        self.assertEqual(self.login(HTTP_ORIGIN="null").status_code, 403)
        self.assertEqual(self.login(HTTP_SEC_FETCH_SITE="cross-site").status_code, 403)

    def test_reading_is_not_affected(self):
        response = self.client.get("/api/learning/units", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, 401)  # refused for the missing token, not as cross-site

    def test_the_refusal_is_in_the_learners_language(self):
        response = self.login(HTTP_ORIGIN="https://evil.example", HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(response.json()["detail"], "Запрос с другого сайта отклонён.")


class LessonCopySizeTests(TestCase):
    @override_settings(LESSON_COPY_MAX_CHARS=100)
    def test_an_oversized_copy_is_refused(self):
        user = User.objects.create_user(email="big@example.test", password="Str0ng-Passphrase!")
        unit = Unit.objects.create(code="01", slug="u", title="U", order=1)
        lesson = Lesson.objects.create(unit=unit, slug="l", title="L", order=1)
        auth = {"HTTP_AUTHORIZATION": "Bearer " + encode_access_token(user, uuid.uuid4())}
        url = f"/api/learning/lessons/{lesson.id}/save"
        big = self.client.post(url, data=json.dumps({"content": "x" * 101}), content_type="application/json", **auth)
        small = self.client.post(url, data=json.dumps({"content": "<p>ok</p>"}), content_type="application/json", **auth)
        self.assertEqual((big.status_code, small.status_code), (413, 200))


class ProductionStartupChecksTests(SimpleTestCase):
    """Production refuses to start half-configured (checked in a fresh process)."""

    def start(self, **env):
        base = {k: v for k, v in os.environ.items() if k not in ("DEBUG", "VERCEL", "DATABASE_URL", "DB_HOST", "ALLOWED_HOSTS")}
        base.update({"DJANGO_SETTINGS_MODULE": "config.settings", "SECRET_KEY": "s" * 40, "JWT_SIGNING_KEY": "j" * 40})
        base.update(env)
        code = "import django; django.setup(); print('started')"
        run = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=BACKEND, env=base, capture_output=True, text=True, timeout=120)
        return run.stdout + run.stderr

    def test_debug_is_refused_on_vercel(self):
        self.assertIn("DEBUG must be off on Vercel", self.start(VERCEL="1", DEBUG="1", DATABASE_URL="postgres://u:p@h/db"))

    def test_vercel_needs_its_database(self):
        self.assertIn("DATABASE_URL is required on Vercel", self.start(VERCEL="1", DEBUG="0"))

    def test_a_wildcard_host_list_is_refused(self):
        self.assertIn("ALLOWED_HOSTS must list", self.start(DEBUG="0", ALLOWED_HOSTS="*"))

    def test_weak_keys_are_refused(self):
        self.assertIn("SECRET_KEY is too weak", self.start(DEBUG="0", SECRET_KEY="123"))
