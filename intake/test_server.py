import hashlib
from http.client import HTTPConnection
from http.server import HTTPServer
import json
from threading import Thread
import unittest
from unittest.mock import patch

import server


class IntakeTest(unittest.TestCase):
    def test_authentication_validation_and_private_issue_receipt(self):
        token = "t" * 64
        server.Handler.token_hashes = (hashlib.sha256(token.encode()).hexdigest(),)
        server.Handler.github_token = "fake-github-token"
        httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
        thread = Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        body = "## Human priority feedback\n\nCase: case-1\nGoal: Choose a plan\n\nSource: user_feedback\n"
        item = {"id": "case-1", "title": "[priority-eval] case-1", "body": body}

        def post(payload, upload_token=None):
            client = HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            headers = {"Content-Type": "application/json"}
            if upload_token:
                headers["Authorization"] = "Bearer " + upload_token
            client.request("POST", "/v1/cases", body=json.dumps(payload), headers=headers)
            result = client.getresponse()
            content = json.loads(result.read())
            client.close()
            return result.status, content

        try:
            with patch.object(server, "create_issue", return_value="I_private_123") as github:
                self.assertEqual(post(item)[0], 401)
                self.assertEqual(post({**item, "body": body + "secret"}, token)[0], 201)
                self.assertEqual(post({**item, "artifact": "/private/file"}, token)[0], 400)
                github.assert_called_once_with({**item, "body": body + "secret"}, "fake-github-token")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
