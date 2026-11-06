"""Language-independent nightly selection on synthetic private conversations."""
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_acceptance import D, T0, FakeHost, Kernel, make_home, packets, review


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

    def test_review_keeps_earlier_assistant_messages(self):
        ref = self.host.add("chat", "user", "Что переживёт рестарт?", T0 - 30)
        self.host.add("chat", "assistant", "Доставка durable, процесс сам не возобновится.", T0 - 29)
        self.host.add("chat", "assistant", "Все пять файлов восстановлены.", T0 - 28)
        self.host.add("chat", "user", "Спасибо", T0 - 20)
        first, second = review.candidates(self.kernel, T0)
        self.assertIn("процесс сам не возобновится", first["reply"])
        self.assertIn("пять файлов", first["reply"])
        self.assertIn("процесс сам не возобновится", second["previous_reply"])
        self.assertEqual(first["pointer"], ref)
        packet = self.kernel.build_packet("nightly")
        original = self.kernel.read(packet["id"], "review:" + ref)
        self.assertIn("процесс сам не возобновится", original["text"])
        self.assertNotIn("Спасибо", original["text"])

    def test_final_batch_gets_earlier_findings_and_empty_queue_can_summarize(self):
        for i in range(11):
            self.host.add(f"chat{i}", "user", "Проверим", T0 - 30 + i)
        first = self.kernel.build_packet("nightly")
        results = [{"candidate_ref": i["ref"], "verdict": "agent_gap" if n == 0 else "fine",
                    "reason": "Unverified claim" if n == 0 else "No issue"}
                   for n, i in enumerate(first["items"])]
        self.kernel.submit(first["id"], results)
        packets.close(self.kernel, first["id"], "ok", T0)
        last = self.kernel.build_packet("nightly")
        self.assertEqual(last["context"]["remaining"], 0)
        self.assertEqual([r["reason"] for r in last["context"]["review_results"]], ["Unverified claim"])
        self.kernel.submit(last["id"], [{"candidate_ref": last["items"][0]["ref"], "verdict": "fine", "reason": "Fine"}])
        packets.close(self.kernel, last["id"], "failed", T0)
        retry = self.kernel.build_packet("nightly")
        self.assertEqual(retry["items"], [])
        self.assertEqual(retry["context"]["review_results"], last["context"]["review_results"])
        packets.close(self.kernel, retry["id"], "ok", T0)
        self.assertIsNone(self.kernel.build_packet("nightly")["id"])

    def test_summary_bound_does_not_drop_results_with_equal_timestamps(self):
        for i in range(23):
            review.record(self.kernel, f"review:chat:{i}", "latent_need" if i == 0 else "friction", f"Observation {i}", T0)
        first = review.unreported(self.kernel, T0)
        self.assertEqual(len(first), 20)
        review.reported(self.kernel, first)
        rest = review.unreported(self.kernel, T0)
        self.assertEqual(len(rest), 3)
        self.assertFalse({r["ref"] for r in first} & {r["ref"] for r in rest})
        self.assertIn("latent_need", {r["verdict"] for r in first + rest})
        review.reported(self.kernel, rest)
        self.assertEqual(review.unreported(self.kernel, T0), [])


class ReviewTurnRead(unittest.TestCase):
    @unittest.skipUnless(find_spec("hermes_state"), "native Hermes source required")
    def test_original_turn_read_is_complete_private_redacted_and_bounded(self):
        import sqlite3
        from hermes_state import SessionDB
        from hermes_muse.host import HostAdapter

        with tempfile.TemporaryDirectory(prefix="muse-review-read-") as tmp:
            home = Path(tmp)
            SessionDB(db_path=home / "state.db").close()
            with sqlite3.connect(home / "state.db") as db:
                db.executemany("INSERT INTO sessions(id,source,chat_type,started_at) VALUES(?,?,?,0)",
                               [("chat", "telegram", "dm"), ("group", "telegram", "group")])
                ref = db.execute("INSERT INTO messages(session_id,role,content,timestamp) VALUES('chat','user','Durability?',1)").lastrowid
                db.executemany("INSERT INTO messages(session_id,role,content,timestamp) VALUES('chat',?,?,?)", [
                    ("assistant", "Process will not resume. api_key=secret12345", 1),
                    ("user", "[IMPORTANT: Background process completed]", 1.5),
                    ("assistant", "Recovered files. " + "x" * 13000, 2),
                    ("user", "Next question", 3), ("assistant", "Unrelated reply", 4)])
                db.execute("INSERT INTO messages(session_id,role,content,timestamp,display_kind) "
                           "VALUES('chat','user','Injected event',1.7,'internal_notification')")
                hidden = db.execute("INSERT INTO messages(session_id,role,content,timestamp) VALUES('group','user','Private',1)").lastrowid
            host = HostAdapter(home)
            first = host.sessions.read(f"chat:{ref}", turn=True)
            self.assertIn("Process will not resume", first["text"])
            self.assertIn("Recovered files", first["text"])
            self.assertNotIn("Background process", first["text"])
            self.assertNotIn("Injected event", first["text"])
            self.assertNotIn("secret12345", first["text"])
            self.assertTrue(first["more"])
            self.assertLessEqual(len(first["text"]), 12000)
            rest = host.sessions.read(f"chat:{ref}", offset=12000, turn=True)
            self.assertFalse(rest["more"])
            self.assertNotIn("Next question", rest["text"])
            self.assertNotIn("Unrelated reply", rest["text"])
            self.assertEqual(host.sessions.read(f"chat:{ref}")["text"], "Durability?")
            self.assertFalse(host.sessions.read(f"group:{hidden}", turn=True)["available"])


if __name__ == "__main__":
    unittest.main()
