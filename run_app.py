from __future__ import annotations

import os
import sys
from pathlib import Path


TORCH_ENV_PYTHON = Path(r"D:\Learning\Conda\envs\torch\python.exe")


def _relaunch_in_torch_env_if_needed() -> None:
    current = Path(sys.executable)
    if not TORCH_ENV_PYTHON.exists():
        return
    if os.path.normcase(str(current)) == os.path.normcase(str(TORCH_ENV_PYTHON)):
        return

    script = Path(__file__).resolve()
    os.execv(str(TORCH_ENV_PYTHON), [str(TORCH_ENV_PYTHON), str(script), *sys.argv[1:]])


if __name__ == "__main__":
    _relaunch_in_torch_env_if_needed()
    from screen_recognition_app.app import main

    raise SystemExit(main())
