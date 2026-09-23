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
            archive = [json.loads(line) for line in (store / "user_messages.jsonl").read_text().splitlines()]
            self.assertEqual(len(found), 1)
            self.assertEqual(len(archive), 2)
            self.assertEqual(found[0]["message"], correction)
            self.assertEqual(found[0]["previous_user"], "能否部署？")
            self.assertEqual(found[0]["previous_assistant"], "可以部署。")
            self.assertEqual(found[0]["status"], "candidate_only")
            self.assertEqual(len(list(discover.candidates_from_text("信息要全面", "user", "input:1"))), 1)
            self.assertFalse((store / "cases").exists())


if __name__ == "__main__":
    unittest.main()
