from pathlib import Path
import re

import genanki
import gdown

# Compatibility across genanki releases.
if not hasattr(genanki.Model, "STANDARD"):
    genanki.Model.STANDARD = genanki.Model.FRONT_BACK

# gdown 6 removed the older fuzzy keyword.
_original_download = gdown.download

def _compatible_download(*args, **kwargs):
    kwargs.pop("fuzzy", None)
    return _original_download(*args, **kwargs)

gdown.download = _compatible_download

script = Path(__file__).with_name("build_decks.py")
source = script.read_text(encoding="utf-8")

# Public build copies in the user's link-shared temporary workspace.
source = source.replace("1tpNLSvDcJUx0McmWiLpt8xTePeVJd1OB", "1fHakVRBpkVmjhr3RvA3QEHwRV7XuOs6o")
source = source.replace("1lbWoXqb_tleGdSRP0QIisHpXde4uFdkk", "1RF9-QVVH4VZUrJuGfKwtVJrkGA2VqBR8")
# Standardized source decks used only to inherit the shared note types and styling.
source = source.replace("1BLh4HkPnUEpwVa-7AaZYhKrttNa2p363", "1Kz_cvHYU3LPDx5VvwGRk0bnzuWHwsGmO")
source = source.replace("1fIC9_LN1Vac5qBMhdF9DB6WYLopAqxJv", "1Xa8q6_XXXtzdGbDSOwmyh31dKzFOv0Hh")
source = source.replace("1iX31-Lv52dFqYvpOXTr5MkKmj2UbdvwW", "1Kz_cvHYU3LPDx5VvwGRk0bnzuWHwsGmO")

# The Breast Imaging school questions reuse lecture cases. Map every image-bearing
# historical question to the matching lecture crop, so all of them appear during
# JBL learning without publishing the complete school exam bank.
source = re.sub(
    r'^EXAM_PDF = download_drive\([^\n]+\)$',
    'EXAM_PDF = BREAST_PDF',
    source,
    flags=re.MULTILINE,
)

replacement = '''# Every image-bearing Breast Imaging exam question from 2019-2026 is surfaced in JBL.
# The school questions reuse the lecture cases, so each slot points to its matching lecture crop.
breast_exam_imgs: dict[str, str] = {
    "2026_q71_us": breast_imgs["case_us"],
    "2026_q72_mammo": breast_imgs["case_mammo"],
    "2023_q94_mammo": breast_imgs["cat5_mammo"],
    "2022_q96_mammo": breast_imgs["case_mammo"],
    "2022_q97_implant": breast_imgs["case_mri"],
    "2021_q93_mammo": breast_imgs["cat5_mammo"],
    "2021_q94_implant": breast_imgs["case_mri"],
    "2019_q63_mammo": breast_imgs["cat5_mammo"],
    "2019_q64_wire": breast_imgs["wire"],
}

mammo_exam_gallery ='''
source, count = re.subn(
    r'# Every image-bearing Breast Imaging exam question from 2019-2026 is extracted and surfaced in JBL\..*?mammo_exam_gallery =',
    replacement,
    source,
    flags=re.DOTALL,
)
if count != 1:
    raise RuntimeError(f"Could not replace Breast Imaging exam media block; matches={count}")

namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(source, str(script), "exec"), namespace)
