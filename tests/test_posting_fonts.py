from io import BytesIO
import unittest
from unittest.mock import patch

import pandas as pd
from PIL import Image, ImageFont

from all_seeing_eye.daily_hub.presentation import png_bytes


class PostingFontTests(unittest.TestCase):
    def test_export_without_installed_fonts(self):
        original = ImageFont.truetype

        def unavailable_system_font(font, *args, **kwargs):
            if isinstance(font, str):
                raise OSError("No system fonts installed")
            return original(font, *args, **kwargs)

        with patch.object(ImageFont, "truetype", side_effect=unavailable_system_font):
            content = png_bytes(pd.DataFrame({"player": ["Sample Player"], "rank": [1]}))
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 100)
            self.assertGreater(image.height, 40)
            self.assertGreater(len(image.getcolors(image.width * image.height)), 1)
