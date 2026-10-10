from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from all_seeing_eye.profit_lens_app import render_app


render_app(ROOT)
