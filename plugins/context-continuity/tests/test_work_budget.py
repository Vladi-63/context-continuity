import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from work_budget import MAX_TAIL, measure, snapshot

TID = "00000000-0000-4000-8000-000000000001"


def event(kind, **fields):
    return (json.dumps({"type": "event_msg", "payload": {"type": kind, **fields}}) + "\n").encode()


def usage(n, window=1000):
    return event("token_count", info={"model_context_window": window, "last_token_usage": {"total_tokens": n},
                                      "total_token_usage": {"total_tokens": 99999}})


def context(turn):
    return (json.dumps({"type": "turn_context", "payload": {"turn_id": turn, "root_turn_id": turn}})
            + "\n").encode()


START = event("task_started", turn_id="turn")
DONE = event("task_complete", turn_id="turn")
COMPACT = b'{"timestamp":"now","type":"compacted","payload":{"message":"never returned"}}\n'


class WorkBudgetTests(unittest.TestCase):
    def test_exact_thresholds_use_active_context(self):
        for count, state in ((299, "READY"), (300, "COMPACT"), (349, "COMPACT"), (350, "HOLD")):
            with self.subTest(count=count):
                result = measure((START, usage(count), DONE))
                self.assertEqual(result["state"], state)
                self.assertEqual(result["tokens"], count)

    def test_new_active_or_aborted_turn_never_reuses_old_sample(self):
        rows = (START, usage(70), DONE, event("task_started", turn_id="next"))
        self.assertEqual(measure(rows)["state"], "BUSY")
        self.assertEqual(measure((*rows, event("turn_aborted", turn_id="next")))["state"], "UNKNOWN")

    def test_compaction_invalidates_counter_until_fresh_usage(self):
        rows = (START, usage(400), COMPACT)
        self.assertEqual(measure((*rows, DONE))["state"], "UNKNOWN")
        result = measure((*rows, usage(100), DONE))
        self.assertEqual(result["state"], "READY")
        self.assertEqual(result["observed_compaction"]["before"], 400)
        self.assertEqual(result["observed_compaction"]["after"], 100)
        self.assertNotIn("never returned", json.dumps(result))

    def test_snapshot_binds_cutoff_to_exact_completed_turn_across_compaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            day = root / "2026/11/19"
            day.mkdir(parents=True)
            path = day / f"rollout-1-{TID}.jsonl"
            filler = b'{"type":"response_item","payload":{"text":"' + b"x" * MAX_TAIL + b'"}}\n'
            rows = (START, filler, context("turn"), usage(95614, 258400), COMPACT,
                    context("turn"), usage(17734, 258400))
            path.write_bytes(b"".join((*rows, DONE)))
            result = snapshot(root, TID)
            self.assertEqual((result["state"], result["turn"], result["percent"]), ("READY", "turn", 6.86))
            self.assertEqual(result["observed_compaction"],
                             {"time": "now", "turn": "turn", "before": 95614, "after": 17734, "window": 258400})
            path.write_bytes(b"".join((*rows, event("task_complete", turn_id="other"))))
            result = snapshot(root, TID)
            self.assertEqual(result["state"], "BUSY")
            self.assertNotIn("observed_compaction", result)
            path.write_bytes(b"".join((*rows, DONE, context("next"), usage(50))))
            self.assertEqual(snapshot(root, TID)["state"], "BUSY")

    def test_context_cannot_inherit_unbound_usage_or_mix_conflicting_turns(self):
        for rows in (
            (usage(100), context("turn"), DONE),
            (context("turn"), usage(100), context("other"), DONE),
            (context("turn"), usage(400), COMPACT, context("other"), usage(100), DONE),
            (START, usage(100), DONE, context("turn"), usage(100), DONE),
        ):
            with self.subTest(rows=rows):
                result = measure(rows)
                self.assertEqual(result["state"], "UNKNOWN")
                self.assertNotIn("observed_compaction", result)

    def test_missing_boundary_partial_data_and_wrong_turn_fail_closed(self):
        self.assertEqual(measure((usage(100), DONE))["state"], "UNKNOWN")
        self.assertEqual(measure((START, usage(100), DONE[:-1]))["state"], "UNKNOWN")
        self.assertEqual(measure((START, usage(100), event("task_complete", turn_id="other")))["state"], "BUSY")

    def test_snapshot_is_targeted_and_requires_a_unique_local_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            day = root / "2026/11/19"
            day.mkdir(parents=True)
            data = START + usage(310) + DONE
            (day / f"rollout-1-{TID}.jsonl").write_bytes(data)
            self.assertEqual(snapshot(root, TID)["state"], "COMPACT")
            self.assertEqual(snapshot(root, "../*")["state"], "UNKNOWN")
            (day / f"rollout-2-{TID}.jsonl").write_bytes(data)
            self.assertEqual(snapshot(root, TID)["state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
