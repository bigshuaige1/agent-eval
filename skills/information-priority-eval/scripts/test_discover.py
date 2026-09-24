import contextlib
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import discover


class DiscoverTest(unittest.TestCase):
    def test_collects_user_correction_with_context_without_creating_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "codex"
            home.mkdir()
            correction = "你漏了关键约束：这个设备不支持。"
            (home / "history.jsonl").write_text(json.dumps({"text": correction}) + "\n")
            sessions = home / "sessions"
            sessions.mkdir()
            rows = [
                {"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "能否部署？"}]}},
                {"type": "response_item", "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "可以部署。"}]}},
                {"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": correction}]}},
            ]
            (sessions / "one.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
            store = root / "store"
            with patch.object(sys, "argv", ["discover.py", "--codex-home", str(home), "--store", str(store)]), \
                 contextlib.redirect_stdout(StringIO()):
                discover.main()
            found = [json.loads(line) for line in (store / "discovery.jsonl").read_text().splitlines()]
            self.assertEqual(len(found), 1)
            self.assertFalse((store / "user_messages.jsonl").exists())
            self.assertEqual(found[0]["message"], correction)
            self.assertEqual(found[0]["previous_user"], "能否部署？")
            self.assertEqual(found[0]["previous_assistant"], "可以部署。")
            self.assertEqual(found[0]["status"], "candidate_only")
            self.assertEqual(len(list(discover.candidates_from_text("信息要全面", "user", "input:1"))), 1)
            self.assertEqual(len(list(discover.candidates_from_text("actually instead 尽可能", "user", "input:1"))), 0)
            self.assertFalse(discover.direct_user_text("[31] tool exec result: instead"))
            self.assertTrue(discover.direct_user_text("[Fe2S2] 不需要低精度"))
            long_text = "x" * 3000 + correction
            self.assertLessEqual(len(next(discover.candidates_from_text(long_text, "user", "input:2"))["message"]), 1200)
            with patch.object(sys, "argv", ["discover.py", "--codex-home", str(home),
                                            "--store", str(store), "--include-all-messages"]), \
                 contextlib.redirect_stdout(StringIO()):
                discover.main()
            archive = [json.loads(line) for line in (store / "user_messages.jsonl").read_text().splitlines()]
            self.assertEqual(len(archive), 2)
            self.assertFalse((store / "cases").exists())


if __name__ == "__main__":
    unittest.main()
