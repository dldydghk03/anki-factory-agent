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
source = script.read_text(encoding="utf-8")
# These copies live inside the user's shared study workspace and inherit its
# link permissions; the private source files remain unchanged.
source = source.replace("1tpNLSvDcJUx0McmWiLpt8xTePeVJd1OB", "1raCcBgDpXgw3hnXSEjHnLjabkh2NgY6i")
source = source.replace("1lbWoXqb_tleGdSRP0QIisHpXde4uFdkk", "1oYXMxzJfWii0mnNTaOXldAQ-BLfg9O-C")
source = source.replace("1iAdIOlAOVrMqXb15g-1xa8nylsjjrrPS", "1q2hBDWVLidgZvB7XyozBiyMrYnSAFa9Y")
namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(source, str(script), "exec"), namespace)
