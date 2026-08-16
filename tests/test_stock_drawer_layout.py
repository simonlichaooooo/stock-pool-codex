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


if __name__ == "__main__":
    unittest.main()
