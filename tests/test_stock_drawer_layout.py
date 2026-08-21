import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class StockDrawerLayoutTests(unittest.TestCase):
    def test_editor_is_wider_while_research_note_is_twenty_percent_narrower(self):
        self.assertIn(".valuation-layout { grid-template-columns: max-content 400px;", HTML)
        self.assertIn("width: 640px !important;", HTML)
        result_panel = HTML.split(".result-panel {", 2)[2].split("}", 1)[0]
        self.assertIn("top: 0;", result_panel)
        self.assertIn("<label>研究备注</label>", HTML)
        self.assertNotIn("<label>个人研究备注</label>", HTML)

    def test_segment_fields_use_requested_proportions(self):
        self.assertIn(
            "grid-template-columns: 132px 112px 52px 76px minmax(0, 1fr) 16px;",
            HTML,
        )
        self.assertIn(
            ".segment-row .amount-field { grid-template-columns: minmax(0, 1fr) 58px; }",
            HTML,
        )
        self.assertIn("font-size: 9.5px;", HTML)

    def test_theme_switcher_is_hidden_while_any_overlay_is_open(self):
        self.assertIn(
            "body:has(.drawer.open, .history-modal.open, .simple-modal-backdrop, .market-insight-detail-drawer) .theme-dock { display:none; }",
            HTML,
        )

    def test_all_stock_editor_number_inputs_hide_native_stepper_controls(self):
        self.assertIn('.drawer input[type="number"] {', HTML)
        self.assertIn("appearance: textfield;", HTML)
        self.assertIn('.drawer input[type="number"]::-webkit-inner-spin-button,', HTML)
        self.assertIn('.drawer input[type="number"]::-webkit-outer-spin-button {', HTML)
        self.assertIn("-webkit-appearance: none;", HTML)

    def test_research_note_has_markdown_formatting_toolbar(self):
        self.assertIn('aria-label="研究备注字体编辑"', HTML)
        for markdown_format in ("bold", "h1", "h2", "h3", "divider"):
            self.assertIn(f'data-markdown-format="{markdown_format}"', HTML)
        self.assertIn("function formatResearchNote(format)", HTML)
        self.assertIn('contenteditable="true"', HTML)
        self.assertIn('data-rich-field="researchNote"', HTML)
        self.assertNotIn('<textarea class="markdown-note"', HTML)
        self.assertIn("function markdownToEditorHtml(markdown)", HTML)
        self.assertIn("function editorHtmlToMarkdown(editor)", HTML)
        self.assertIn('document.execCommand("bold", false)', HTML)
        self.assertIn('document.execCommand("formatBlock", false, format.toUpperCase())', HTML)
        self.assertIn('document.execCommand("insertHorizontalRule", false)', HTML)

    def test_research_notes_support_multiple_sorted_entries(self):
        self.assertIn("function sortedResearchNotes", HTML)
        self.assertIn("new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0)", HTML)
        self.assertIn("function researchNoteTitle", HTML)
        self.assertIn('data-action="newResearchNote"', HTML)
        self.assertIn('data-action="editResearchNote"', HTML)
        self.assertIn('data-action="deleteResearchNote"', HTML)
        self.assertIn('data-action="saveResearchNote"', HTML)
        self.assertIn("max-height: 260px;", HTML)
        self.assertIn("overflow-y: auto;", HTML)


if __name__ == "__main__":
    unittest.main()
