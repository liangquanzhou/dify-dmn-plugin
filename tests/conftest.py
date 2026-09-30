import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))

# Match production SDK bootstrap order to avoid late gevent monkey patching.
import dify_plugin  # noqa: E402,F401
