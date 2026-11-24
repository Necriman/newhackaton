"""A person checks a startup and sets its verdict; junk intakes show as such."""
from django.core.cache import cache
from django.test import TestCase

from adminpanel.models import AuditLog
from startup.models import StartupProfile

from .tests import Client, make_user

JUNK = {"name": "фвы", "location": "Tashkent", "stage": "mvp", "market": "b2b", "team": "large",
        "problem": "выф\nвфы", "description": "ывф", "alternatives": "выф", "revenue_model": "ывф"}


class StartupReviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_user("owner@example.test", role="owner")
        self.analyst = make_user("analyst@example.test", role="analyst")
        founder = make_user("ali@example.test")
        self.p = StartupProfile.objects.create(user=founder, name="фвы", onboarding=JUNK, onboarding_completed=True,
                                               blocks={"research": {"verdict": "uncertain", "summary": "B2B market..."}})
        self.url = f"/api/admin/startups/{self.p.pk}"

    def test_a_junk_intake_shows_as_not_enough_to_judge(self):
        owner = Client(self, self.owner)
        owner.unlock()
        row = owner.get("/api/admin/startups").json()["results"][0]
        self.assertEqual((row["verdict"], row["reviewed"]), ("insufficient", False))

    def test_the_owner_sets_the_verdict_and_can_undo_it(self):
        owner = Client(self, self.owner)
        owner.unlock()
        res = owner.send("post", self.url + "/review", {"verdict": "weak", "note": "Пустая анкета"})
        body = res.json()
        self.assertEqual(res.status_code, 200, body)
        self.assertEqual((body["verdict"], body["reviewed"], body["review"]["note"], body["review"]["ai_verdict"]),
                         ("weak", True, "Пустая анкета", "uncertain"))
        self.p.refresh_from_db()
        self.assertEqual(self.p.blocks["research"]["verdict"], "weak")  # filters and counts follow
        self.assertEqual(owner.get("/api/admin/startups", data={"verdict": "weak"}).json()["results"][0]["id"], str(self.p.pk))
        self.assertTrue(AuditLog.objects.filter(action="startup.reviewed").exists())

        self.assertEqual(owner.send("post", self.url + "/review", {"verdict": "great"}).status_code, 400)
        back = owner.send("post", self.url + "/review", {"clear": True}).json()
        self.assertIsNone(back["review"])
        self.p.refresh_from_db()
        self.assertEqual(self.p.blocks["research"]["verdict"], "uncertain")

    def test_an_analyst_can_look_but_not_set(self):
        analyst = Client(self, self.analyst)
        analyst.unlock()
        self.assertEqual(analyst.get(self.url).status_code, 200)
        self.assertEqual(analyst.send("post", self.url + "/review", {"verdict": "strong"}).status_code, 403)
