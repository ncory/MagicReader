"""The web UI pages: each browser tab is titled with the reader's short hostname,
"hm4-reader - MagicReader", so several readers open at once can be told apart."""
import os
import types
import unittest

import _support  # noqa: F401

PAGES = ("/", "/bands.html", "/sequences.html", "/sounds.html", "/settings.html", "/backup.html")


class PageTitleTests(unittest.TestCase):
    """Through Flask's test client - needs Flask, as on a Pi."""

    @classmethod
    def setUpClass(cls):
        try:
            import flask  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Flask is not installed")

    def setUp(self):
        import api
        self.api = api
        # Flask("MagicReaderApi") finds templates/ from the working directory,
        # which is the repo root when the app runs as a service
        self.cwd = os.getcwd()
        os.chdir(_support.REPO_DIR)
        self.realNode = api.platform.node
        api.platform.node = lambda: "hm4-reader.local"
        captured = []
        realServe = api.serveApp
        api.serveApp = lambda app, port: captured.append(app)
        try:
            api.RunMagicApi(types.SimpleNamespace(), port=80)
        finally:
            api.serveApp = realServe
        self.client = captured[0].test_client()

    def tearDown(self):
        self.api.platform.node = self.realNode
        os.chdir(self.cwd)

    def test_every_page_is_titled_with_the_short_hostname(self):
        for page in PAGES:
            with self.subTest(page=page):
                html = self.client.get(page).get_data(as_text=True)
                self.assertIn("<title>hm4-reader - MagicReader</title>", html)

    def test_the_navbar_still_shows_the_full_address(self):
        html = self.client.get("/bands.html").get_data(as_text=True)
        self.assertIn("http://hm4-reader.local:80/", html)


if __name__ == "__main__":
    unittest.main()
