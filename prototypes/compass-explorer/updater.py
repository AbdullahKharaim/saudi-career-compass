"""Compatibility entry point; canonical implementation is compass.local_update."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from compass.local_update import *
