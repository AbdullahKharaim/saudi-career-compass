"""Compatibility entry point; canonical implementation is compass.verify."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from compass.verify import *
if __name__ == "__main__":
    sys.exit(main())
