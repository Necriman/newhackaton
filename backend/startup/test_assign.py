"""Handing a task to an employee: the letter, the employee's page, the founder's view."""
import json
import re
import uuid
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.jwt_utils import encode_access_token
from accounts.models import User

from .models import Assignment, Employee, StartupProfile


@override_settings(APP_ORIGIN="https://zinvest.uz")
class AssignTaskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.founder = User.objects.create_user(email="founder@example.test", password="Str0ng-Passphrase!", first_name="Dilshod")
        StartupProfile.objects.create(user=self.founder, name="Non Uyi Bakery")
        self.auth = {"HTTP_AUTHORIZATION": "Bearer " + encode_access_token(self.founder, uuid.uuid4())}
        self.employee = Employee.objects.create(user=self.founder, full_name="Aziza Rahimova", email="aziza@example.test")

    def call(self, method, path, data=None, auth=True, **headers):
        kwargs = {"content_type": "application/json", **(self.auth if auth else {}), **headers}
        if data is not None:
            kwargs["data"] = json.dumps(data)
        return getattr(self.client, method)("/api/startup/" + path, **kwargs)

    def assign(self, **extra):
        body = {"employee": str(self.employee.id), "title": "Order flour for December", "description": "Two suppliers, compare prices.",
                "priority": "high", "end_date": "2026-12-01", **extra}
        return self.call("post", "assignments", body)

    def secret_from_letter(self, letter):
        return re.search(r"/task/([A-Za-z0-9_\-]+)", letter.body).group(1)

    # ----- the founder hands it out ------------------------------------------
    def test_assigning_mails_the_employee_a_link_to_the_task(self):
        response = self.assign()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["letter"]["sent"], body["letter"]["to"]), (True, "aziza@example.test"))
        self.assertEqual((body["assignment"]["priority"], body["assignment"]["status"]), ("high", "new"))
        self.assertIsNotNone(body["assignment"]["notified_at"])

        self.assertEqual(len(mail.outbox), 1)
        letter = mail.outbox[0]
        self.assertEqual(letter.to, ["aziza@example.test"])
        self.assertIn("Dilshod", letter.subject)
        self.assertIn("Order flour for December", letter.subject)
        self.assertIn("https://zinvest.uz/task/", letter.body)
        self.assertIn("Non Uyi Bakery", letter.alternatives[0][0])
        # Only a hash of the link is kept.
        secret = self.secret_from_letter(letter)
        self.assertNotIn(secret, Assignment.objects.get().token_hash)

    def test_no_address_no_letter_and_the_founder_is_told_why(self):
        self.employee.email = ""
        self.employee.save()
        body = self.assign().json()
        self.assertEqual(body["letter"], {"sent": False, "reason": "no_email", "to": ""})
        self.assertEqual(len(mail.outbox), 0)

    def test_the_founder_can_skip_the_letter(self):
        self.assertEqual(self.assign(notify=False).json()["letter"]["reason"], "skipped")
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_input_is_refused(self):
        self.assertEqual(self.assign(priority="asap").status_code, 400)
        self.assertEqual(self.assign(title="  ").status_code, 400)
        bad = self.call("post", "employees", {"full_name": "X", "email": "not-an-address"})
        self.assertEqual(bad.status_code, 400)

    # ----- the employee's page -----------------------------------------------
    def test_the_employee_reads_the_task_and_moves_it_along(self):
        self.assign()
        secret = self.secret_from_letter(mail.outbox[0])
        page = self.call("get", f"task/{secret}", auth=False).json()["task"]
        self.assertEqual((page["title"], page["priority"], page["founder_name"], page["business_name"]),
                         ("Order flour for December", "high", "Dilshod", "Non Uyi Bakery"))
        self.assertNotIn("employee_email", page)

        for status in ("accepted", "in_progress"):
            self.assertEqual(self.call("post", f"task/{secret}", {"status": status}, auth=False).json()["task"]["status"], status)
        done = self.call("post", f"task/{secret}", {"status": "done", "note": "Ordered from Uzdon, 30 bags."}, auth=False).json()["task"]
        self.assertEqual((done["status"], done["note"]), ("done", "Ordered from Uzdon, 30 bags."))

        board = self.call("get", "assignments").json()["assignments"][0]
        self.assertEqual((board["status"], board["done"], board["note"]), ("done", True, "Ordered from Uzdon, 30 bags."))

    def test_a_wrong_link_finds_nothing(self):
        response = self.call("get", "task/not-a-real-secret", auth=False, HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual((response.status_code, response.json()["detail"]), (404, "Ссылка на задачу больше не действует."))

    def test_the_employee_cannot_set_anything_else(self):
        self.assign()
        secret = self.secret_from_letter(mail.outbox[0])
        self.assertEqual(self.call("post", f"task/{secret}", {"status": "new"}, auth=False).status_code, 400)
        self.call("post", f"task/{secret}", {"title": "Changed", "priority": "low"}, auth=False)
        task = Assignment.objects.get()
        self.assertEqual((task.title, task.priority), ("Order flour for December", "high"))

    def test_sending_again_replaces_the_link(self):
        task_id = self.assign().json()["assignment"]["id"]
        old = self.secret_from_letter(mail.outbox[0])
        self.assertEqual(self.call("post", f"assignments/{task_id}/notify").status_code, 200)
        new = self.secret_from_letter(mail.outbox[1])
        self.assertNotEqual(old, new)
        self.assertEqual(self.call("get", f"task/{old}", auth=False).status_code, 404)
        self.assertEqual(self.call("get", f"task/{new}", auth=False).status_code, 200)

    def test_the_employee_can_stop_the_letters(self):
        task_id = self.assign().json()["assignment"]["id"]
        secret = self.secret_from_letter(mail.outbox[0])
        self.assertTrue(self.call("post", f"task/{secret}", {"letters_off": True}, auth=False).json()["task"]["letters_off"])
        again = self.call("post", f"assignments/{task_id}/notify")
        self.assertEqual((again.status_code, again.json()["letter"]["reason"]), (409, "opted_out"))
        # A new address on the card is a new person: letters go out again.
        self.call("put", f"employees/{self.employee.id}", {"email": "aziza.new@example.test"})
        self.assertEqual(self.call("post", f"assignments/{task_id}/notify").status_code, 200)

    # ----- the founder's board ------------------------------------------------
    def test_ticking_done_on_the_board_moves_the_status(self):
        task_id = self.assign(notify=False).json()["assignment"]["id"]
        self.assertEqual(self.call("patch", f"assignments/{task_id}", {"done": True}).json()["assignment"]["status"], "done")
        body = self.call("patch", f"assignments/{task_id}", {"status": "in_progress", "priority": "low"}).json()["assignment"]
        self.assertEqual((body["status"], body["done"], body["priority"]), ("in_progress", False, "low"))

    def test_another_founder_cannot_touch_the_task(self):
        task_id = self.assign().json()["assignment"]["id"]
        other = User.objects.create_user(email="other@example.test", password="Str0ng-Passphrase!")
        auth = {"HTTP_AUTHORIZATION": "Bearer " + encode_access_token(other, uuid.uuid4())}
        self.assertEqual(self.client.post(f"/api/startup/assignments/{task_id}/notify", **auth).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/startup/assignments/{task_id}", data="{}", content_type="application/json", **auth).status_code, 404)

    def test_letters_are_rate_limited_per_founder(self):
        with mock.patch("startup.assign.LETTERS_PER_HOUR", 2):
            reasons = [self.assign(title=f"Task {n}").json()["letter"]["reason"] for n in range(3)]
        self.assertEqual(reasons, ["", "", "rate_limited"])
        self.assertEqual(len(mail.outbox), 2)
