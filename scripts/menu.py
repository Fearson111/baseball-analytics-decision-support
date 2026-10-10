from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from all_seeing_eye.menu import main


if __name__ == "__main__":
    raise SystemExit(main())
