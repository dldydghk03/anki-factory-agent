from pathlib import Path

import genanki
import gdown

# Compatibility across genanki releases.
if not hasattr(genanki.Model, "STANDARD"):
    genanki.Model.STANDARD = genanki.Model.FRONT_BACK

# gdown 6 removed the older fuzzy keyword. Keep the main build script
# compatible with both older and newer releases.
_original_download = gdown.download

def _compatible_download(*args, **kwargs):
    kwargs.pop("fuzzy", None)
    return _original_download(*args, **kwargs)

gdown.download = _compatible_download

script = Path(__file__).with_name("build_decks.py")
namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
