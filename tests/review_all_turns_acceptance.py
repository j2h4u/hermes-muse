"""Language-independent nightly selection on synthetic private conversations."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_acceptance import D, T0, FakeHost, Kernel, make_home, review


class ReviewAllTurns(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="muse-review-all-")
        self.addCleanup(temporary.cleanup)
        self.host = FakeHost(lambda: T0)
        self.kernel = Kernel(make_home(Path(temporary.name)), adapter=self.host, clock=lambda: T0)

    def test_every_language_reaches_the_model_with_context(self):
        first = self.host.add("ru", "user", "К поездке хорошо бы вернуться заранее", T0 - 30)
        self.host.add("ru", "assistant", "Обсудим накануне отъезда.", T0 - 29)
        second = self.host.add("ru", "user", "Тогда выбирать билеты будет поздновато", T0 - 20)
        self.host.add("ru", "assistant", "Понимаю.", T0 - 19)
        english = self.host.add("en", "user", "The departure date is approaching", T0 - 10)
        japanese = self.host.add("ja", "user", "旅行の日程について相談したいです", T0 - 5)

        candidates = review.candidates(self.kernel, T0)
        self.assertEqual([item["pointer"] for item in candidates], [first, second, english, japanese])
        followup = next(item for item in candidates if item["pointer"] == second)
        self.assertEqual(followup["previous_reply"], "Обсудим накануне отъезда.")
        self.assertEqual(followup["previous_user"], "К поездке хорошо бы вернуться заранее")

    def test_review_once_window_and_machine_exclusion(self):
        self.host.add("old", "user", "Старая беседа", T0 - 4 * D)
        self.host.add("scheduled", "user", "Фоновое задание", T0 - 20, source="cron")
        first = self.host.add("chat", "user", "Просто поговорим", T0 - 10)
        second = self.host.add("chat", "user", "Хорошего вечера", T0 - 5)
        candidates = review.candidates(self.kernel, T0)
        self.assertEqual([item["pointer"] for item in candidates], [first, second])
        review.record(self.kernel, "review:" + first, "fine", "No action needed", T0)
        self.assertEqual([item["pointer"] for item in review.candidates(self.kernel, T0)], [second])
        self.assertEqual(review.candidates(self.kernel, T0, skip=["review:" + second]), [])
        self.assertEqual(review.candidates(self.kernel, T0 + D)[0]["pointer"], second)

    def test_tool_failures_are_hints_not_a_selection_gate(self):
        failed = self.host.add("failed", "user", "Проверим состояние", T0 - 30)
        self.host.add("failed", "tool", '{"success": false, "error": "timeout"}', T0 - 29, tool="terminal")
        retried = self.host.add("retried", "user", "Проверим другое", T0 - 20)
        self.host.add("retried", "tool", '{"success": false, "error": "timeout"}', T0 - 19, tool="terminal")
        self.host.add("retried", "tool", '{"success": true}', T0 - 18, tool="terminal")
        candidates = review.candidates(self.kernel, T0)
        self.assertEqual([item["pointer"] for item in candidates], [failed, retried])
        self.assertEqual(candidates[0]["rules"], ["tool_failure_unretried"])
        self.assertEqual(candidates[1]["rules"], [])


if __name__ == "__main__":
    unittest.main()
