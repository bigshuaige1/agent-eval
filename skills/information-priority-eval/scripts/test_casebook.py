import contextlib
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
from types import SimpleNamespace

import casebook


class CasebookTest(unittest.TestCase):
    def test_partial_feedback_does_not_enter_rate_and_private_ref_is_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            case = {"schema_version": 1, "id": "feedback-1", "goal": "Decide whether to deploy",
                    "review_scope": "partial", "artifact": "/private/source.md",
                    "requirements": [{"finding": "Device limit omitted", "source": "user_feedback",
                                      "importance": "critical", "status": "missing", "stage": "selection",
                                      "impact": "Could choose an unsupported device"}]}
            casebook.save(store, case)
            with self.assertRaises(FileExistsError):
                casebook.save(store, case)
            out = StringIO()
            with contextlib.redirect_stdout(out):
                casebook.report(store)
            self.assertIn("Critical omissions in complete reviews: 0/0", out.getvalue())
            self.assertNotIn("/private/source.md", casebook.issue_body(case))
            case["id"] = "review-1"
            case["review_scope"] = "complete"
            case["requirements"][0]["source"] = "independent_review"
            casebook.save(store, case)
            out = StringIO()
            with contextlib.redirect_stdout(out):
                casebook.report(store)
            self.assertIn("Critical omissions in complete reviews: 1/1 (100.0%)", out.getvalue())

    def test_publish_needs_enter_and_does_not_repeat_sent_case(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            case = {"schema_version": 1, "id": "share-1", "goal": "Choose a plan",
                    "review_scope": "partial", "artifact": "/private/artifact.md",
                    "requirements": [{"finding": "A required condition was omitted",
                                      "source": "user_feedback", "importance": "critical",
                                      "status": "missing", "stage": "selection"}]}
            casebook.save(store, case)
            base = ["casebook.py", "publish", "--store", str(store), "--id", "share-1",
                    "--repo", "example/feedback"]
            with patch.object(sys, "argv", base), \
                 patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: False)), \
                 patch.object(casebook.request, "urlopen") as send:
                with contextlib.redirect_stdout(StringIO()):
                    casebook.main()
                send.assert_not_called()
            class Response:
                def __enter__(self):
                    return StringIO('{"html_url":"https://github.com/example/feedback/issues/1"}')

                def __exit__(self, *_):
                    return False

            with patch.object(sys, "argv", base), \
                 patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: True)), \
                 patch("builtins.input", return_value=""), \
                 patch.dict("os.environ", {"GH_TOKEN": "fake-token"}), \
                 patch.object(casebook.request, "urlopen", return_value=Response()) as send:
                with contextlib.redirect_stdout(StringIO()):
                    casebook.main()
                sent = send.call_args.args[0]
                self.assertEqual(sent.full_url, "https://api.github.com/repos/example/feedback/issues")
                self.assertNotIn("/private/artifact.md", sent.data.decode())
                self.assertEqual(len(casebook.pending_cases(store, "example/feedback")), 0)
                self.assertEqual(casebook.policy_mode(store, "example/feedback"), "manual")
                self.assertFalse(casebook.claim_path(store, "example/feedback", "share-1").exists())
                with contextlib.redirect_stdout(StringIO()):
                    casebook.main()
                send.assert_called_once()

    def test_claim_blocks_concurrent_submission_until_reconciled(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            case = {"schema_version": 1, "id": "uncertain-1", "goal": "Choose a plan",
                    "review_scope": "partial", "requirements": [{"finding": "Condition omitted",
                    "source": "user_feedback", "importance": "critical", "status": "missing",
                    "stage": "selection"}]}
            casebook.save(store, case)
            claim = casebook.claim_path(store, "example/feedback", "uncertain-1")
            claim.parent.mkdir(parents=True)
            claim.write_text("submission started\n")
            self.assertEqual(casebook.pending_cases(store, "example/feedback"), [])
            with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}), \
                 patch.object(casebook.request, "urlopen") as send:
                with self.assertRaises(FileExistsError):
                    casebook.submit_case(store, "example/feedback", case)
                send.assert_not_called()
            argv = ["casebook.py", "resolve", "--store", str(store), "--repo", "example/feedback",
                    "--id", "uncertain-1", "--issue-url",
                    "https://github.com/example/feedback/issues/12"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(StringIO()):
                casebook.main()
            self.assertFalse(claim.exists())
            self.assertEqual(casebook.pending_cases(store, "example/feedback"), [])

    def test_watch_rechecks_after_the_default_one_hour_interval(self):
        argv = ["casebook.py", "watch", "--store", "/unused", "--repo", "example/feedback"]
        with patch.object(sys, "argv", argv), \
             patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: True)), \
             patch.object(casebook, "review_and_sync") as review, \
             patch.object(casebook.time, "sleep", side_effect=KeyboardInterrupt) as sleep:
            with self.assertRaises(KeyboardInterrupt), contextlib.redirect_stdout(StringIO()):
                casebook.main()
            review.assert_called_once_with(Path("/unused"), "example/feedback", max_batch=10)
            sleep.assert_called_once_with(3600)

    def test_failed_receipt_write_keeps_claim_without_false_sent_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            case = {"schema_version": 1, "id": "receipt-1", "goal": "Choose a plan",
                    "review_scope": "partial", "requirements": [{"finding": "Limit omitted",
                    "source": "user_feedback", "importance": "critical", "status": "missing",
                    "stage": "selection"}]}
            casebook.save(store, case)
            class Response:
                def __enter__(self):
                    return StringIO('{"html_url":"https://github.com/example/feedback/issues/13"}')

                def __exit__(self, *_):
                    return False

            with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}), \
                 patch.object(casebook.request, "urlopen", return_value=Response()), \
                 patch.object(casebook.os, "link", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    casebook.submit_case(store, "example/feedback", case)
            self.assertTrue(casebook.claim_path(store, "example/feedback", "receipt-1").exists())
            self.assertFalse(casebook.receipt_path(store, "example/feedback", "receipt-1").exists())

    def test_resolve_rejects_invalid_case_id(self):
        argv = ["casebook.py", "resolve", "--store", "/unused", "--repo", "example/feedback",
                "--id", "../../escape", "--not-created"]
        with patch.object(sys, "argv", argv), self.assertRaisesRegex(ValueError, "invalid case id"):
            casebook.main()

    def test_existing_github_cli_login_can_supply_token(self):
        with patch.dict("os.environ", {"GH_TOKEN": "", "GITHUB_TOKEN": ""}), \
             patch.object(casebook.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(casebook.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0, stdout="local-token\n")) as run:
            self.assertEqual(casebook.github_token(), "local-token")
            run.assert_called_once()

    def test_publish_defaults_to_maintainer_repository(self):
        argv = ["casebook.py", "publish", "--store", "/unused", "--id", "case-1"]
        with patch.object(sys, "argv", argv), patch.object(casebook, "review_and_sync") as review:
            casebook.main()
        review.assert_called_once_with(Path("/unused"), "bigshuaige1/agent-eval",
                                       selected="case-1", max_batch=1)

    def test_always_opt_in_persists_for_noninteractive_sync_and_can_be_revoked(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            repo = "example/feedback"

            def add_case(case_id):
                casebook.save(store, {"schema_version": 1, "id": case_id, "goal": "Choose a plan",
                    "review_scope": "partial", "requirements": [{"finding": "Limit omitted",
                    "source": "user_feedback", "importance": "critical", "status": "missing",
                    "stage": "selection"}]})

            class Response:
                def __enter__(self):
                    return StringIO('{"html_url":"https://github.com/example/feedback/issues/1"}')

                def __exit__(self, *_):
                    return False

            add_case("case-one")
            with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}), \
                 patch.object(casebook.request, "urlopen", return_value=Response()) as send:
                with patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: True)), \
                     patch("builtins.input", return_value="ALWAYS"), \
                     contextlib.redirect_stdout(StringIO()):
                    casebook.review_and_sync(store, repo)
                self.assertEqual(casebook.policy_mode(store, repo), "auto")
                self.assertEqual(casebook.policy_mode(store, "other/repo"), "manual")
                add_case("case-two")
                with patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: False)), \
                     patch("builtins.input", side_effect=AssertionError("unexpected prompt")), \
                     contextlib.redirect_stdout(StringIO()):
                    casebook.review_and_sync(store, repo)
                self.assertEqual(send.call_count, 2)
                argv = ["casebook.py", "policy", "--store", str(store), "--repo", repo, "--manual"]
                with patch.object(sys, "argv", argv), contextlib.redirect_stdout(StringIO()):
                    casebook.main()
                self.assertEqual(casebook.policy_mode(store, repo), "manual")
                add_case("case-three")
                with patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: False)), \
                     contextlib.redirect_stdout(StringIO()):
                    casebook.review_and_sync(store, repo)
                self.assertEqual(send.call_count, 2)

    def test_watch_allows_noninteractive_run_after_auto_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            casebook.set_policy(store, "example/feedback", "auto")
            argv = ["casebook.py", "watch", "--store", str(store), "--repo", "example/feedback"]
            with patch.object(sys, "argv", argv), \
                 patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: False)), \
                 patch.object(casebook, "review_and_sync") as review, \
                 patch.object(casebook.time, "sleep", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt), contextlib.redirect_stdout(StringIO()):
                    casebook.main()
                review.assert_called_once()

    def test_lowercase_always_does_not_grant_ongoing_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            casebook.save(store, {"schema_version": 1, "id": "not-approved", "goal": "Choose a plan",
                "review_scope": "partial", "requirements": [{"finding": "Limit omitted",
                "source": "user_feedback", "importance": "critical", "status": "missing",
                "stage": "selection"}]})
            with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}), \
                 patch.object(casebook.sys, "stdin", SimpleNamespace(isatty=lambda: True)), \
                 patch("builtins.input", return_value="always"), \
                 patch.object(casebook.request, "urlopen") as send, \
                 contextlib.redirect_stdout(StringIO()):
                casebook.review_and_sync(store, "example/feedback")
            send.assert_not_called()
            self.assertEqual(casebook.policy_mode(store, "example/feedback"), "manual")


if __name__ == "__main__":
    unittest.main()
