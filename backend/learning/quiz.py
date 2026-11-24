"""
The check after a lesson.

Pressing "Lesson complete" opens a short test on that lesson. The lesson only
counts as done, with its coins and streak day, once the learner reaches the
pass mark (3 of 4), and the next lesson of the unit stays closed until then.
A failed attempt says which questions were wrong but not the right answers,
so the way through is re-reading the lesson, not guessing.

The questions live on the lesson (Lesson.quiz) in English, Russian and Uzbek,
with the choices in the same order in every language. They are written once
from the lesson's own text (manage.py generate_lesson_quizzes) and shipped in
content/lesson_quizzes.json (manage.py import_lesson_quizzes).
"""
import re

from django.conf import settings

LANGS = ("en", "ru", "uz")
QUESTIONS = 4
CHOICES = 4


def pass_mark(total):
    """Correct answers needed: 3 of 4 (LESSON_QUIZ_PASS_RATIO = 0.75)."""
    from math import ceil

    return max(1, ceil(total * settings.LESSON_QUIZ_PASS_RATIO - 1e-9))


def questions_of(lesson):
    return (lesson.quiz or {}).get("questions") or []


def has_quiz(lesson):
    return bool(questions_of(lesson))


def _text(q, lang):
    return q.get(lang) or q.get("en") or {}


def public(lesson, lang):
    """The questions to show: no answers, no explanations."""
    out = []
    for q in questions_of(lesson):
        t = _text(q, lang)
        out.append({"id": q["id"], "prompt": t.get("prompt", ""), "choices": list(t.get("choices") or [])})
    return out


def state(lesson, progress, lang):
    """What the lesson page needs: the questions and where the learner stands."""
    questions = public(lesson, lang)
    if not questions:
        return None
    best = progress.quiz_best if progress else None
    need = pass_mark(len(questions))
    return {
        "questions": questions,
        "total": len(questions),
        "pass_mark": need,
        "best": best,
        "attempts": progress.quiz_attempts if progress else 0,
        "passed": best is not None and best >= need,
    }


def grade(lesson, lang, answers):
    """
    answers: [{"question_id", "choice_index"}]. Returns (correct, total, results);
    results say per question whether it was right, and only for right ones why.
    """
    given = {}
    for a in answers if isinstance(answers, list) else []:
        if isinstance(a, dict) and isinstance(a.get("question_id"), str) and isinstance(a.get("choice_index"), int):
            given[a["question_id"]] = a["choice_index"]
    results, correct = [], 0
    for q in questions_of(lesson):
        ok = given.get(q["id"]) == q.get("answer_index")
        correct += ok
        results.append({"id": q["id"], "correct": ok, "explanation": _text(q, lang).get("explanation", "") if ok else ""})
    return correct, len(results), results


def blocked_by(user, lesson, completed=None):
    """The earlier lesson of the same unit still to finish, or None. A lesson
    already done is always open (for going back over it)."""
    from .services import completed_lesson_ids

    done = completed if completed is not None else completed_lesson_ids(user)
    if lesson.id in done:
        return None
    for earlier in lesson.unit.lessons.filter(order__lt=lesson.order).order_by("order"):
        if earlier.id not in done:
            return earlier
    return None


# --------------------------------------------------------------------------- #
# Checking what the model wrote (generate_lesson_quizzes)
# --------------------------------------------------------------------------- #
_OG = re.compile(r"([oOgG])['`ʻ’‘]")
_TUTUQ = re.compile(r"(?<=\w)['`ʼ](?=\w)")


def _uz(text):
    """Uzbek as the app writes it: o‘ and g‘ with ‘, the tutuq belgisi as ’."""
    return _TUTUQ.sub("’", _OG.sub(r"\1‘", text))


def clean(raw):
    """A model answer -> the stored quiz, or None if anything is off."""
    items = (raw or {}).get("questions") if isinstance(raw, dict) else None
    if not isinstance(items, list) or len(items) != QUESTIONS:
        return None
    questions = []
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            return None
        index = item.get("answer_index")
        if not isinstance(index, int) or not 0 <= index < CHOICES:
            return None
        q = {"id": f"q{n}", "answer_index": index}
        for lang in LANGS:
            t = item.get(lang)
            if not isinstance(t, dict):
                return None
            prompt = str(t.get("prompt") or "").strip()
            choices = [str(c).strip() for c in t.get("choices") or []]
            explanation = str(t.get("explanation") or "").strip()
            if not prompt or len(prompt) > 300 or len(choices) != CHOICES or any(not c or len(c) > 200 for c in choices):
                return None
            if len({c.lower() for c in choices}) != CHOICES:
                return None
            if lang == "uz":
                prompt, explanation = _uz(prompt), _uz(explanation)
                choices = [_uz(c) for c in choices]
            q[lang] = {"prompt": prompt, "choices": choices, "explanation": explanation[:400]}
        questions.append(q)
    if len({q["answer_index"] for q in questions}) == 1:  # every answer in the same place: lazy, redo
        return None
    if sum(_longest(q["en"]["choices"]) == q["answer_index"] for q in questions) > QUESTIONS // 2:
        return None  # "pick the longest answer" would pass it
    return {"questions": questions}


def _longest(choices):
    """The index of the one choice longer than all the others, or None."""
    lengths = [len(c) for c in choices]
    top = max(lengths)
    return lengths.index(top) if lengths.count(top) == 1 else None


def key(lesson):
    """A lesson's name in content/lesson_quizzes.json. Lesson slugs repeat across
    units (every unit has its own "glossary"), so the unit's slug comes first."""
    return f"{lesson.unit.slug}/{lesson.slug}"


def recheck(stored):
    """A stored quiz run through clean() again, as the model would have written it."""
    questions = (stored or {}).get("questions") if isinstance(stored, dict) else None
    if not isinstance(questions, list):
        return None
    return clean({"questions": [{k: v for k, v in q.items() if k != "id"} for q in questions if isinstance(q, dict)]})
