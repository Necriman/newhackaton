"""
Load the after-lesson checks from content/lesson_quizzes.json onto the lessons.

    python manage.py import_lesson_quizzes            write them
    python manage.py import_lesson_quizzes --dry-run  only say what would change

Lessons are matched by "unit-slug/lesson-slug"; every check is validated again
before it is saved.
"""
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from learning import quiz
from learning.management.commands.generate_lesson_quizzes import FILE
from learning.models import Lesson


class Command(BaseCommand):
    help = "Load the after-lesson checks from content/lesson_quizzes.json."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        data = json.loads(FILE.read_text(encoding="utf-8"))
        changed = same = bad = 0
        missing = []
        with transaction.atomic():
            for name, stored in data.items():
                unit_slug, _, slug = name.partition("/")
                lessons = list(Lesson.objects.filter(unit__slug=unit_slug, slug=slug))
                if not lessons:
                    missing.append(name)
                    continue
                clean = quiz.recheck(stored)  # what the file holds goes through the same checks again
                if not clean:
                    bad += 1
                    continue
                for lesson in lessons:
                    if lesson.quiz == clean:
                        same += 1
                        continue
                    changed += 1
                    if not opts["dry_run"]:
                        lesson.quiz = clean
                        lesson.save(update_fields=["quiz"])
            if opts["dry_run"]:
                transaction.set_rollback(True)
        without = Lesson.objects.filter(quiz={}).count()
        self.stdout.write(f"changed {changed}, unchanged {same}, invalid {bad}, unknown lessons {len(missing)}, lessons still without a check {without}"
                          + (" (dry run)" if opts["dry_run"] else ""))
        for name in missing[:10]:
            self.stdout.write(f"  unknown: {name}")
