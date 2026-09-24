import unittest

import render


class RenderTest(unittest.TestCase):
    def test_external_https_manifest_has_matching_host_and_tls(self):
        text = render.render("intake.example.com", "registry.example.com/intake:v1", "intake-tls", "nginx")
        self.assertIn("image: registry.example.com/intake:v1", text)
        self.assertEqual(text.count("intake.example.com"), 2)
        self.assertIn("secretName: intake-tls", text)
        self.assertIn("ingressClassName: nginx", text)
        self.assertNotIn("intake.example.invalid", text)
        with self.assertRaises(ValueError):
            render.render("intake.example.invalid", "registry.example.com/intake:v1", "intake-tls")


if __name__ == "__main__":
    unittest.main()
