"""The check after a lesson: it completes the lesson, and the next one waits for it."""
import io
import json
import tempfile
import uuid
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from accounts.jwt_utils import encode_access_token
from accounts.models import User

from . import quiz
from .models import Lesson, LessonProgress, Unit, UserStats

ANSWERS = [1, 0, 3, 2]


def raw_quiz(answers=ANSWERS):
    """A quiz in the shape the model writes it."""
    questions = []
    for n, right in enumerate(answers, 1):
        item = {"answer_index": right}
        for lang, word in (("en", "Question"), ("ru", "Вопрос"), ("uz", "Savol")):
            item[lang] = {
                "prompt": f"{word} {n}?",
                "choices": [f"{word} {n} choice {c}" for c in range(4)],
                "explanation": f"{word} {n} because.",
            }
        questions.append(item)
    return {"questions": questions}


class CleanTests(SimpleTestCase):
    def test_a_good_answer_is_kept_with_stable_ids(self):
        stored = quiz.clean(raw_quiz())
        self.assertEqual([q["id"] for q in stored["questions"]], ["q1", "q2", "q3", "q4"])
        self.assertEqual([q["answer_index"] for q in stored["questions"]], ANSWERS)

    def test_anything_off_is_refused(self):
        three = raw_quiz()
        three["questions"].pop()
        same_choices = raw_quiz()
        same_choices["questions"][0]["ru"]["choices"][1] = same_choices["questions"][0]["ru"]["choices"][0]
        no_uzbek = raw_quiz()
        del no_uzbek["questions"][2]["uz"]
        out_of_range = raw_quiz([1, 0, 4, 2])
        for bad in (three, same_choices, no_uzbek, out_of_range, raw_quiz([2, 2, 2, 2]), None, {"questions": "x"}):
            self.assertIsNone(quiz.clean(bad))

    def test_the_right_answer_must_not_be_the_longest_every_time(self):
        raw = raw_quiz()
        for q in raw["questions"][:3]:
            q["en"]["choices"][q["answer_index"]] += " with a much longer and more careful wording"
        self.assertIsNone(quiz.clean(raw))
        raw["questions"][2]["en"]["choices"][0] += " and a long wrong one that is even longer than the right one"
        self.assertIsNotNone(quiz.clean(raw))  # two of four is chance, not a giveaway

    def test_uzbek_gets_the_apps_apostrophes(self):
        raw = raw_quiz()
        raw["questions"][0]["uz"]["prompt"] = "To'g'ri ma'lumot qaysi?"
        self.assertEqual(quiz.clean(raw)["questions"][0]["uz"]["prompt"], "To‘g‘ri ma’lumot qaysi?")

    def test_the_pass_mark_is_three_of_four(self):
        self.assertEqual([quiz.pass_mark(n) for n in (1, 2, 4, 5)], [1, 2, 3, 4])


class LessonQuizTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="quiz@example.test", password="Str0ng-Passphrase!")
        self.auth = {"HTTP_AUTHORIZATION": "Bearer " + encode_access_token(self.user, uuid.uuid4())}
        self.unit = Unit.objects.create(code="01", slug="basics", title="Basics", order=1)
        self.first = Lesson.objects.create(unit=self.unit, slug="one", title="Lesson one", order=1,
                                           coin_reward=10, quiz=quiz.clean(raw_quiz()))
        self.second = Lesson.objects.create(unit=self.unit, slug="two", title="Lesson two", order=2, coin_reward=10)

    def post(self, path, data, **headers):
        return self.client.post("/api/learning/" + path, data=json.dumps(data), content_type="application/json",
                                **self.auth, **headers)

    def get(self, lesson, **headers):
        return self.client.get(f"/api/learning/lessons/{lesson.id}", **self.auth, **headers)

    def answer(self, choices, **headers):
        answers = [{"question_id": f"q{n}", "choice_index": c} for n, c in enumerate(choices, 1)]
        return self.post(f"lessons/{self.first.id}/quiz", {"answers": answers}, **headers)

    def coins(self):
        return UserStats.objects.get_or_create(user=self.user)[0].coins

    def test_the_lesson_shows_its_check_without_the_answers(self):
        body = self.get(self.first).json()
        check = body["quiz"]
        self.assertEqual((check["total"], check["pass_mark"], check["passed"], check["best"]), (4, 3, False, None))
        self.assertEqual(set(check["questions"][0]), {"id", "prompt", "choices"})
        self.assertNotIn("answer_index", json.dumps(body))
        russian = self.get(self.first, HTTP_ACCEPT_LANGUAGE="ru").json()["quiz"]["questions"][0]
        self.assertEqual(russian["prompt"], "Вопрос 1?")

    def test_the_next_lesson_waits_for_the_one_before(self):
        response = self.get(self.second)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "lesson_locked")
        self.assertEqual(response.json()["blocked_by"], {"id": str(self.first.id), "title": "Lesson one"})
        self.assertEqual(self.post(f"lessons/{self.second.id}/complete", {}).status_code, 403)
        ru = self.get(self.second, HTTP_ACCEPT_LANGUAGE="ru").json()
        self.assertEqual(ru["detail"], "Сначала пройдите предыдущий урок.")

    def test_the_catalogue_marks_what_is_closed(self):
        def closed():
            units = self.client.get("/api/learning/lessons", **self.auth).json()["units"]
            return [les["closed"] for les in units[0]["lessons"]]

        self.assertEqual(closed(), [False, True])
        self.answer(ANSWERS)
        self.assertEqual(closed(), [False, False])

    def test_pressing_complete_asks_for_the_check(self):
        response = self.post(f"lessons/{self.first.id}/complete", {})
        self.assertEqual((response.status_code, response.json()["code"]), (409, "quiz_required"))
        self.assertFalse(LessonProgress.objects.filter(user=self.user, status=LessonProgress.Status.COMPLETED).exists())
        self.assertEqual(self.coins(), 0)

    def test_a_miss_says_which_were_wrong_but_not_the_answers(self):
        body = self.answer([1, 0, 0, 0]).json()  # two of four
        self.assertEqual((body["correct"], body["total"], body["passed"]), (2, 4, False))
        self.assertNotIn("completion", body)
        self.assertEqual([r["correct"] for r in body["results"]], [True, True, False, False])
        self.assertEqual(body["results"][2]["explanation"], "")
        self.assertNotIn("answer_index", json.dumps(body))
        progress = LessonProgress.objects.get(user=self.user, lesson=self.first)
        self.assertEqual((progress.status, progress.quiz_best, progress.quiz_attempts),
                         (LessonProgress.Status.IN_PROGRESS, 2, 1))
        self.assertEqual(self.get(self.second).status_code, 403)
        self.assertEqual(self.coins(), 0)

    def test_the_pass_mark_completes_the_lesson_once(self):
        body = self.answer([1, 0, 3, 0], HTTP_ACCEPT_LANGUAGE="ru").json()  # three of four
        self.assertTrue(body["passed"])
        self.assertEqual(body["results"][0]["explanation"], "Вопрос 1 because.")
        self.assertEqual(body["completion"]["coins_awarded"], 10)
        self.assertEqual(body["completion"]["unlocked_next"]["lesson_id"], str(self.second.id))
        self.assertEqual(self.get(self.second).status_code, 200)
        state = self.get(self.first).json()
        self.assertEqual((state["status"], state["quiz"]["passed"], state["quiz"]["best"]), ("completed", True, 3))

        again = self.answer(ANSWERS).json()  # going over it again earns nothing more
        self.assertEqual(again["completion"]["coins_awarded"], 0)
        self.assertEqual(self.coins(), 10)
        self.assertEqual(self.post(f"lessons/{self.first.id}/complete", {}).status_code, 200)

    def test_a_lesson_without_a_check_completes_as_before(self):
        LessonProgress.objects.create(user=self.user, lesson=self.first, status=LessonProgress.Status.COMPLETED)
        response = self.post(f"lessons/{self.second.id}/complete", {})
        self.assertEqual((response.status_code, response.json()["coins_awarded"]), (200, 10))
        self.assertEqual(self.post(f"lessons/{self.second.id}/quiz", {"answers": []}).status_code, 404)

    def test_junk_answers_and_too_many_tries(self):
        for junk in ({"answers": "all"}, {"answers": [{"question_id": 1}] * 60}, ["x"]):
            self.assertEqual(self.post(f"lessons/{self.first.id}/quiz", junk).status_code, 400)
        self.assertEqual(self.answer([None, "1", 9, -1]).json()["correct"], 0)
        statuses = [self.answer([0, 0, 0, 0]).status_code for _ in range(20)]
        self.assertEqual(statuses[-1], 429)
        self.assertTrue(self.user.__class__.objects.get(pk=self.user.pk).is_active)  # retrying is never a ban


class ImportTests(TestCase):
    def test_the_file_is_checked_and_matched_by_slug(self):
        unit = Unit.objects.create(code="01", slug="basics", title="Basics", order=1)
        other = Unit.objects.create(code="02", slug="more", title="More", order=2)
        lesson = Lesson.objects.create(unit=unit, slug="glossary", title="Glossary", order=1)
        twin = Lesson.objects.create(unit=other, slug="glossary", title="Glossary", order=1)  # same slug, other unit
        Lesson.objects.create(unit=unit, slug="two", title="Lesson two", order=2)
        bad = raw_quiz([0, 0, 0, 0])
        data = {"basics/glossary": quiz.clean(raw_quiz()), "basics/gone": quiz.clean(raw_quiz()), "basics/two": bad}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lesson_quizzes.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with mock.patch("learning.management.commands.import_lesson_quizzes.FILE", path):
                out = io.StringIO()
                call_command("import_lesson_quizzes", "--dry-run", stdout=out)
                lesson.refresh_from_db()
                self.assertEqual(lesson.quiz, {})
                call_command("import_lesson_quizzes", stdout=out)
        lesson.refresh_from_db()
        twin.refresh_from_db()
        self.assertEqual([q["answer_index"] for q in lesson.quiz["questions"]], ANSWERS)
        self.assertEqual(twin.quiz, {})  # the other unit's glossary is a different lesson
        self.assertIn("changed 1, unchanged 0, invalid 1, unknown lessons 1", out.getvalue())
