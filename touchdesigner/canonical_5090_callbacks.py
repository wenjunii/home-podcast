"""Shared Show Control with canonical playback locked off for live generation."""
from pathlib import Path
import time

_shared = Path(project.folder) / "touchdesigner/show_control_callbacks.py"
exec(compile(_shared.read_text(encoding="utf-8"), str(_shared), "exec"), globals())
_shared_write_live_control = _write_live_control


def _write_live_control(*, regenerate=False):
    control = parent()
    control.par.Runtimeprofile = "3080_safe"
    control.par.Livevariations = False
    _connector().par.Runtimeprofile = "3080_safe"
    for attempt in range(6):
        try:
            return _shared_write_live_control(regenerate=False)
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.02 * (attempt + 1))
