from __future__ import annotations

import subprocess
import sys
import time

from .config import VIEWER_HOST, VIEWER_PORT


def main(restart_seconds: int = 8) -> None:
    """Run the viewer in a restart loop (for scheduled tasks / manual worker)."""
    print(f"SysML spec worker on http://{VIEWER_HOST}:{VIEWER_PORT} (restart every {restart_seconds}s on exit)")
    while True:
        proc = subprocess.run([sys.executable, "-m", "sysml_spec_qa", "serve"], check=False)
        print(f"viewer exited code={proc.returncode}; restart in {restart_seconds}s")
        time.sleep(restart_seconds)


if __name__ == "__main__":
    main()
