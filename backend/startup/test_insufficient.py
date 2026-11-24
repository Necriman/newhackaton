"""An intake that says nothing gets no market check and no verdict it did not earn."""
from django.test import SimpleTestCase

from . import research

GOOD = {
    "name": "Non Uyi", "location": "Tashkent", "market": "b2c", "stage": "idea", "team": "solo",
    "problem": "Families in Chilonzor cannot get fresh tandir bread delivered before work.",
    "description": "A bakery app: order the evening before, a courier brings bread by 7 am.",
    "revenue_model": "Bread margin plus a monthly delivery subscription.",
}


class LooksEmptyTests(SimpleTestCase):
    def test_keyboard_mashing_is_refused_before_any_ai_call(self):
        junk = {**GOOD, "problem": "выф\nвфы", "description": "ывф", "revenue_model": "ывф"}
        self.assertTrue(research.looks_empty(junk))
        self.assertEqual(research.validate(junk), research.TOO_THIN)

    def test_a_real_short_answer_passes(self):
        self.assertFalse(research.looks_empty(GOOD))
        self.assertIsNone(research.validate(GOOD))
        # One terse answer is fine when the rest say something.
        self.assertFalse(research.looks_empty({**GOOD, "revenue_model": "Подписка"}))

    def test_the_model_may_say_it_cannot_judge(self):
        self.assertEqual(research._shape({"verdict": "insufficient"}, [], False)["verdict"], "insufficient")
