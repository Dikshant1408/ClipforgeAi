import sys
from pathlib import Path

# Add the project root to sys.path so clipforge can be imported inside tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
