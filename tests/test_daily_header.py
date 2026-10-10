import unittest
from unittest.mock import patch

from all_seeing_eye.daily_hub.app import format_slate_date, page_header


class DailyHeaderTests(unittest.TestCase):
    def test_header_uses_selected_slate_date(self):
        with patch("all_seeing_eye.daily_hub.app.st.html") as render:
            page_header("2026-09-12")
        markup = render.call_args.args[0]
        self.assertIn('<h1 id="daily-baseball">Daily Baseball</h1>', markup)
        self.assertIn('<time datetime="2026-09-12">September 12th, 2026</time>', markup)
        self.assertIn('class="daily-baseball-header"', markup)

    def test_date_ordinals(self):
        for day, suffix in ((1, "st"), (2, "nd"), (3, "rd"), (11, "th"), (12, "th"), (13, "th"), (21, "st")):
            self.assertEqual(format_slate_date(f"2026-09-{day:02d}"), f"September {day}{suffix}, 2026")


if __name__ == "__main__":
    unittest.main()
