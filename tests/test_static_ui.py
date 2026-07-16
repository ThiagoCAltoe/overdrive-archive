from __future__ import annotations

import unittest
from pathlib import Path


STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static"


class StaticInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        cls.javascript = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    def test_archive_library_starts_with_recordings_not_all_categories(self) -> None:
        start = self.html.index('<select id="library-category">')
        end = self.html.index("</select>", start)
        selector = self.html[start:end]

        self.assertIn('<option value="recordings" selected>', selector)
        self.assertIn('<option value="">All categories</option>', selector)
        self.assertNotIn('<option value="" selected>', selector)

    def test_deleted_recordings_are_metadata_only_and_restorable(self) -> None:
        self.assertIn("renderDeletedLocalCard", self.javascript)
        self.assertIn("/api/recordings/restore", self.javascript)
        self.assertIn("Download again", self.javascript)
        self.assertIn("0 B stored", self.javascript)

    def test_restored_recordings_can_return_to_automatic_retention(self) -> None:
        self.assertIn("/api/recordings/release-retention", self.javascript)
        self.assertIn("Use retention rules", self.javascript)
        self.assertIn("Current retention rules may delete", self.javascript)

    def test_portuguese_option_and_translation_catalog_are_present(self) -> None:
        self.assertIn('<option value="pt-BR">Português (Brasil)</option>', self.html)
        self.assertIn("const PT_BR_TEXT", self.javascript)
        self.assertIn("'Deleted locally': 'Apagado localmente'", self.javascript)

    def test_camera_layouts_are_user_configurable(self) -> None:
        self.assertIn('id="recording-layout"', self.html)
        self.assertIn('id="surveillance-layout"', self.html)
        self.assertIn(
            "recording_layout: $('recording-layout').value",
            self.javascript,
        )
        self.assertIn(
            "surveillance_layout: $('surveillance-layout').value",
            self.javascript,
        )

    def test_library_has_incremental_pagination_and_stale_request_cancellation(
        self,
    ) -> None:
        self.assertIn('id="library-load-more"', self.html)
        self.assertIn("new AbortController()", self.javascript)
        self.assertIn("params.set('offset'", self.javascript)
        self.assertIn("loadLibrary({ append: true })", self.javascript)
        self.assertNotIn("params.set('limit', '200')", self.javascript)


if __name__ == "__main__":
    unittest.main()
