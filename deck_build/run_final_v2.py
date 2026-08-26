from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import zstandard as zstd

ROOT = Path(__file__).resolve().parent
base_script = ROOT / "run_builder.py"
code = base_script.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Source corrections
# ---------------------------------------------------------------------------
# Use the final infertility deck as the first template source. The remaining
# shared decks stay available as fallbacks for Basic and exam card layouts.
code = code.replace(
    'source = source.replace("1BLh4HkPnUEpwVa-7AaZYhKrttNa2p363", "1Kz_cvHYU3LPDx5VvwGRk0bnzuWHwsGmO")',
    'source = source.replace("1BLh4HkPnUEpwVa-7AaZYhKrttNa2p363", "1xxPDqykU17XaoBGcP24fBN_nW02vYybg")',
    1,
)

# The previous wrapper substituted lecture images for school-exam images.
# The complete school exam PDF is now available in the bounded build folder,
# so retain the original extraction code and point it to that PDF instead.
exam_mapping_pattern = re.compile(
    r'# The Breast Imaging image questions reuse lecture cases\..*?'
    r'# The standardized exam note type uses Korean field names\.',
    flags=re.DOTALL,
)
exam_mapping_replacement = '''# Use the complete school-exam source for the actual image-bearing questions.
source = source.replace("1iAdIOlAOVrMqXb15g-1xa8nylsjjrrPS", "1Qw2s4JtHiDEJ15I0Snq_nyGz3kzt8kw1")

# The standardized exam note type uses Korean field names.'''
code, exam_mapping_count = exam_mapping_pattern.subn(exam_mapping_replacement, code, count=1)
if exam_mapping_count != 1:
    raise RuntimeError(f"Could not restore the school-exam image extraction block: {exam_mapping_count}")

# Add the newly supplied 74-page pediatric-surgery lecture as the concept-image
# source. The existing summary PDF remains the bounded source for school/KMLE
# question panels and explanations.
lecture_patch = r'''
# Use the newly supplied full pediatric-surgery lecture for concept crops.
source = source.replace(
    'PEDS_PDF = download_drive(DRIVE_IDS["peds_summary"], SRC / "peds_summary.pdf")\n',
    'PEDS_PDF = download_drive(DRIVE_IDS["peds_summary"], SRC / "peds_summary.pdf")\n'
    'PEDS_LECTURE_PDF = download_drive("1TuyVdMJnBZEOX9YGvtIAYOT09EGHDD5E", SRC / "peds_lecture_2026_v2.pdf")\n',
    1,
)

peds_lecture_crops = '''peds_crop_specs = {
    # Understanding images from the full 2026 lecture PDF.
    "warming": (12, (0.02, 0.05, 0.98, 0.95)),
    "tgdc_concept": (18, (0.02, 0.05, 0.98, 0.95)),
    "sistrunk": (19, (0.02, 0.05, 0.98, 0.95)),
    "branchial_types": (20, (0.02, 0.05, 0.62, 0.95)),
    "branchial_photo": (27, (0.05, 0.05, 0.95, 0.78)),
    "lm": (31, (0.02, 0.05, 0.98, 0.95)),
    "nec": (40, (0.02, 0.05, 0.98, 0.95)),
    "nec_tx": (39, (0.02, 0.05, 0.98, 0.95)),
    "red_flags": (43, (0.02, 0.05, 0.98, 0.95)),
    "three_clues": (44, (0.02, 0.05, 0.98, 0.95)),
    "appendix_us": (48, (0.02, 0.05, 0.98, 0.95)),
    "serial_exam": (74, (0.02, 0.05, 0.98, 0.95)),
}
for key, (page, rect) in peds_crop_specs.items():
    peds_imgs[key] = add_media(render_crop(PEDS_LECTURE_PDF, page, rect, f"peds_{key}.png"))
'''
source, crop_count = re.subn(
    r'peds_crop_specs = \{.*?\n# Pediatric question panels/images\.',
    peds_lecture_crops + '\n# Pediatric question panels/images.',
    source,
    count=1,
    flags=re.DOTALL,
)
if crop_count != 1:
    raise RuntimeError(f"Could not replace pediatric concept-crop block: {crop_count}")
'''
needle = '# The standardized exam note type uses Korean field names. Map them explicitly\n'
if needle not in code:
    raise RuntimeError("Could not locate pediatric lecture-patch insertion point")
code = code.replace(needle, lecture_patch + "\n" + needle, 1)

# Remove residual author/producer phrasing while preserving source attribution
# and the original problem text.
neutral_patch = r'''
# Additional neutral wording normalization.
for _old, _new in {
    "왕족입니다": "여러 해 반복 출제되었습니다",
    "왕족": "반복 출제",
    "꼭 기억하세요": "",
    "꼭 기억": "",
    "이 카드에서는": "",
    "익혀야 합니다": "확인합니다",
    "여기서부터가 시험의 진짜 핵심": "",
}.items():
    source = source.replace(_old, _new)
'''
wording_needle = 'for old, new in wording_replacements.items():\n    source = source.replace(old, new)\n'
if wording_needle not in code:
    raise RuntimeError("Could not locate neutral-wording insertion point")
code = code.replace(wording_needle, wording_needle + neutral_patch, 1)

# Use unambiguous final filenames distinct from every prior attempt.
code = code.replace("0826_최종개선판.apkg", "0826_누락검수완료.apkg")

# Execute the patched production build.
namespace = {"__file__": str(base_script), "__name__": "__main__"}
exec(compile(code, str(base_script), "exec"), namespace)

# ---------------------------------------------------------------------------
# Independent post-build validation
# ---------------------------------------------------------------------------
def collection_bytes(apkg: Path) -> bytes:
    with zipfile.ZipFile(apkg) as zf:
        for name in ("collection.anki2", "collection.anki21", "collection.anki21b"):
            if name not in zf.namelist():
                continue
            data = zf.read(name)
            if name.endswith(".anki21b"):
                try:
                    return zstd.ZstdDecompressor().decompress(data)
                except zstd.ZstdError:
                    with zstd.ZstdDecompressor().stream_reader(data) as reader:
                        return reader.read()
            return data
    raise RuntimeError(f"No Anki collection database in {apkg}")


def inspect_apkg(apkg: Path) -> dict[str, object]:
    data = collection_bytes(apkg)
    tmp = Path(tempfile.mkstemp(suffix=".sqlite")[1])
    tmp.write_bytes(data)
    try:
        con = sqlite3.connect(str(tmp))
        cur = con.cursor()
        col = cur.execute("SELECT decks, models FROM col LIMIT 1").fetchone()
        if not col:
            raise AssertionError(f"{apkg.name}: collection metadata missing")
        decks = json.loads(col[0])
        models = json.loads(col[1])
        deck_names = {int(did): cfg["name"] for did, cfg in decks.items()}
        card_counts = {int(did): int(n) for did, n in cur.execute("SELECT did, COUNT(*) FROM cards GROUP BY did")}
        cards_by_name = {name: card_counts.get(did, 0) for did, name in deck_names.items()}
        model_names = {int(mid): cfg.get("name", "") for mid, cfg in models.items()}
        note_rows = cur.execute("SELECT id, mid, flds, tags FROM notes").fetchall()
        all_field_text = "\n".join(row[2] for row in note_rows)
        nonempty_tags = [row[0] for row in note_rows if row[3].strip()]
        con.close()

        with zipfile.ZipFile(apkg) as zf:
            media_map = json.loads(zf.read("media")) if "media" in zf.namelist() else {}
        media_names = set(media_map.values())
        image_refs = set(re.findall(r'<img[^>]+src=["\']([^"\']+)', all_field_text, flags=re.IGNORECASE))
        missing_media = sorted(image_refs - media_names)

        return {
            "cards_by_name": cards_by_name,
            "model_names": set(model_names.values()),
            "note_rows": note_rows,
            "all_text": all_field_text,
            "nonempty_tags": nonempty_tags,
            "image_refs": image_refs,
            "missing_media": missing_media,
        }
    finally:
        tmp.unlink(missing_ok=True)


def require_deck(result: dict[str, object], suffix: str, expected_cards: int | None = None, minimum_cards: int = 1) -> tuple[str, int]:
    cards_by_name: dict[str, int] = result["cards_by_name"]  # type: ignore[assignment]
    matches = [(name, count) for name, count in cards_by_name.items() if name.endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(f"Required deck {suffix!r} not found exactly once: {matches}")
    name, count = matches[0]
    if count < minimum_cards:
        raise AssertionError(f"{name}: expected at least {minimum_cards} cards, found {count}")
    if expected_cards is not None and count != expected_cards:
        raise AssertionError(f"{name}: expected exactly {expected_cards} cards, found {count}")
    return name, count


def validate_exam_fields(result: dict[str, object], required_exam_notes: int) -> None:
    exam_model_names = {"!표준화 뉴족보 ver2.1"}
    model_names: set[str] = result["model_names"]  # type: ignore[assignment]
    if not exam_model_names.issubset(model_names):
        raise AssertionError(f"Exam model missing: {exam_model_names - model_names}")

    # Each standardized exam note uses three visible fields: problem number,
    # question body, and answer/explanation. A missing field previously caused
    # the corresponding subdeck to disappear after import.
    exam_rows = []
    note_rows = result["note_rows"]  # type: ignore[assignment]
    # The model id cannot be inferred from name here without reopening models,
    # so identify exam notes by the three-field structure and the expected HTML.
    for _nid, _mid, flds, _tags in note_rows:
        fields = flds.split("\x1f")
        if len(fields) >= 3 and ("정답:" in fields[-1] or "정답" in fields[-1]) and fields[0].strip():
            exam_rows.append(fields)
    if len(exam_rows) < required_exam_notes:
        raise AssertionError(f"Expected at least {required_exam_notes} populated exam notes, found {len(exam_rows)}")
    for idx, fields in enumerate(exam_rows, start=1):
        if not fields[0].strip() or not fields[1].strip() or not fields[-1].strip():
            raise AssertionError(f"Exam note {idx} contains an empty visible field")


def validate_common(apkg: Path, result: dict[str, object]) -> None:
    if result["nonempty_tags"]:
        raise AssertionError(f"{apkg.name}: notes with tags found: {len(result['nonempty_tags'])}")
    if result["missing_media"]:
        raise AssertionError(f"{apkg.name}: missing embedded media: {result['missing_media']}")
    forbidden = ["왕족", "꼭 기억", "가져갈 한 줄", "이 카드에서는", "여기서부터가 시험의 진짜 핵심"]
    text: str = result["all_text"]  # type: ignore[assignment]
    found = [phrase for phrase in forbidden if phrase in text]
    if found:
        raise AssertionError(f"{apkg.name}: producer-style phrases remain: {found}")


peds_out = Path(namespace["peds_out"])
breast_out = Path(namespace["breast_out"])
peds = inspect_apkg(peds_out)
breast = inspect_apkg(breast_out)

# The expected card counts are exact for non-cloze subdecks. JBL is cloze-based,
# so the minimum reflects the number of meaningful recall cards rather than notes.
peds_counts = [
    require_deck(peds, "::1. JBL", minimum_cards=12),
    require_deck(peds, "::2. 참공", expected_cards=5),
    require_deck(peds, "::3. 족보", expected_cards=6),
    require_deck(peds, "::4. KMLE", expected_cards=12),
]
breast_counts = [
    require_deck(breast, "::1. JBL", minimum_cards=17),
    require_deck(breast, "::2. 족보", expected_cards=20),
]
validate_exam_fields(peds, required_exam_notes=18)
validate_exam_fields(breast, required_exam_notes=20)
validate_common(peds_out, peds)
validate_common(breast_out, breast)

required_peds_models = {"!표준화 cloze ver2.1", "!표준화 Basic ver2.1", "!표준화 뉴족보 ver2.1"}
required_breast_models = {"!표준화 cloze ver2.1", "!표준화 뉴족보 ver2.1"}
if not required_peds_models.issubset(peds["model_names"]):
    raise AssertionError(f"Pediatric standardized models missing: {required_peds_models - peds['model_names']}")
if not required_breast_models.issubset(breast["model_names"]):
    raise AssertionError(f"Breast standardized models missing: {required_breast_models - breast['model_names']}")

out_dir = Path(namespace["OUT"])
validation_report = out_dir / "FINAL_VALIDATION.md"
lines = [
    "# Final APKG validation",
    "",
    "## Pediatric Surgery",
]
for name, count in peds_counts:
    lines.append(f"- `{name}`: **{count} cards**")
lines.extend([
    "- Populated school/KMLE exam notes: **18 or more verified**",
    f"- Embedded image references: **{len(peds['image_refs'])}**, missing: **0**",
    "",
    "## Breast Imaging",
])
for name, count in breast_counts:
    lines.append(f"- `{name}`: **{count} cards**")
lines.extend([
    "- Populated school exam notes: **20 verified**",
    f"- Embedded image references: **{len(breast['image_refs'])}**, missing: **0**",
    "",
    "## Shared checks",
    "- Required subdecks are present and non-empty.",
    "- Standardized note types are present.",
    "- Exam note fields are populated.",
    "- Tags are absent.",
    "- Referenced media are embedded.",
    "- Producer-style phrases checked above are absent.",
])
validation_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(validation_report.read_text(encoding="utf-8"))
