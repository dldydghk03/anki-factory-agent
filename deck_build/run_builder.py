from pathlib import Path
import genanki

# Compatibility across genanki releases.
if not hasattr(genanki.Model, "STANDARD"):
    genanki.Model.STANDARD = genanki.Model.FRONT_BACK

script = Path(__file__).with_name("build_decks.py")
namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
