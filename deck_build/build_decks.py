from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import tempfile
import textwrap
import zipfile
from pathlib import Path
from typing import Any, Iterable

import fitz  # PyMuPDF
import genanki
import gdown
import zstandard as zstd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUT = ROOT / "output"
MEDIA = WORK / "media"
SRC = WORK / "sources"
for p in (WORK, OUT, MEDIA, SRC):
    p.mkdir(parents=True, exist_ok=True)

# Public/shared Google Drive source IDs supplied by the study workspace.
DRIVE_IDS = {
    "peds_summary": "1tpNLSvDcJUx0McmWiLpt8xTePeVJd1OB",
    "breast_lecture": "1lbWoXqb_tleGdSRP0QIisHpXde4uFdkk",
    "linked_exam": "1iAdIOlAOVrMqXb15g-1xa8nylsjjrrPS",
    "template_acute": "1BLh4HkPnUEpwVa-7AaZYhKrttNa2p363",
    "template_complication": "1fIC9_LN1Vac5qBMhdF9DB6WYLopAqxJv",
    "template_vascular": "1iX31-Lv52dFqYvpOXTr5MkKmj2UbdvwW",
}


def download_drive(file_id: str, output: Path) -> Path:
    if output.exists() and output.stat().st_size > 1024:
        return output
    print(f"Downloading {output.name} from Drive id={file_id}")
    result = gdown.download(id=file_id, output=str(output), quiet=False, fuzzy=True)
    if not result or not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(f"Failed to download Drive file {file_id} -> {output}")
    return output


PEDS_PDF = download_drive(DRIVE_IDS["peds_summary"], SRC / "peds_summary.pdf")
BREAST_PDF = download_drive(DRIVE_IDS["breast_lecture"], SRC / "breast_lecture.pdf")
EXAM_PDF = download_drive(DRIVE_IDS["linked_exam"], SRC / "linked_exam.pdf")
TEMPLATE_APKGS = [
    download_drive(DRIVE_IDS["template_acute"], SRC / "template_acute.apkg"),
    download_drive(DRIVE_IDS["template_complication"], SRC / "template_complication.apkg"),
    download_drive(DRIVE_IDS["template_vascular"], SRC / "template_vascular.apkg"),
]


def deterministic_id(text: str, floor: int = 1_000_000_000) -> int:
    value = int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:12], 16)
    return floor + (value % 1_000_000_000)


def extract_sqlite_from_apkg(apkg: Path) -> Path | None:
    with zipfile.ZipFile(apkg) as zf:
        names = zf.namelist()
        candidates = [n for n in names if n in {"collection.anki2", "collection.anki21", "collection.anki21b"}]
        if not candidates:
            return None
        name = candidates[0]
        data = zf.read(name)
        if name.endswith(".anki21b"):
            try:
                data = zstd.ZstdDecompressor().decompress(data)
            except zstd.ZstdError:
                # Some packages use a size-less zstd frame.
                with zstd.ZstdDecompressor().stream_reader(data) as reader:
                    data = reader.read()
        out = Path(tempfile.mkstemp(suffix=".sqlite")[1])
        out.write_bytes(data)
        return out


def read_models(apkg: Path) -> list[dict[str, Any]]:
    db_path = extract_sqlite_from_apkg(apkg)
    if not db_path:
        return []
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(col)").fetchall()]
        models: list[dict[str, Any]] = []
        if "models" in cols:
            raw = cur.execute("SELECT models FROM col LIMIT 1").fetchone()[0]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            obj = json.loads(raw)
            models.extend(obj.values())
        else:
            # Newer schema fallback. It is enough to report names; fallback models below remain usable.
            tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "notetypes" in tables:
                for row in cur.execute("SELECT id, name, config FROM notetypes"):
                    try:
                        cfg = json.loads(row[2]) if isinstance(row[2], str) else {}
                    except Exception:
                        cfg = {}
                    cfg.update({"id": row[0], "name": row[1]})
                    models.append(cfg)
        con.close()
        return models
    except Exception as exc:
        print(f"Could not inspect {apkg.name}: {exc}")
        return []
    finally:
        db_path.unlink(missing_ok=True)


ALL_MODEL_SPECS: list[dict[str, Any]] = []
for apkg in TEMPLATE_APKGS:
    specs = read_models(apkg)
    print(f"Models in {apkg.name}:")
    for spec in specs:
        print("  -", spec.get("name"), "type=", spec.get("type"), "id=", spec.get("id"))
    ALL_MODEL_SPECS.extend(specs)


def fallback_model(kind: str) -> genanki.Model:
    base_css = r"""
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
  font-size: 19px; line-height: 1.58; text-align: left; color: #202124;
  background: #fff; padding: 22px; max-width: 920px; margin: auto;
}
b { font-size: 1.08em; }
.cloze { font-weight: 750; color: #0b66c3; }
img { display: block; max-width: 100%; max-height: 740px; height: auto; margin: 16px auto; border-radius: 8px; }
.extra { border-top: 1px solid #d9dde3; margin-top: 18px; padding-top: 15px; font-size: 0.92em; color: #30343a; }
.exam-label { font-size: 0.82em; color: #68707a; margin: 8px 0; }
.good { background: #eef7ff; padding: 10px 12px; border-radius: 8px; }
.warn { background: #fff5e6; padding: 10px 12px; border-radius: 8px; }
"""
    if kind == "cloze":
        return genanki.Model(
            1708626101,
            "!표준화 cloze ver2.1",
            fields=[{"name": "Text"}, {"name": "Back Extra"}],
            templates=[{
                "name": "Cloze",
                "qfmt": "{{cloze:Text}}",
                "afmt": "{{cloze:Text}}<div class='extra'>{{Back Extra}}</div>",
            }],
            css=base_css,
            model_type=genanki.Model.CLOZE,
        )
    if kind == "basic":
        return genanki.Model(
            1708626102,
            "!표준화 Basic ver2.1",
            fields=[{"name": "Front"}, {"name": "Back"}],
            templates=[{
                "name": "Card 1",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id='answer'>{{Back}}",
            }],
            css=base_css,
        )
    return genanki.Model(
        1708626103,
        "!표준화 뉴족보 ver2.1",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[{
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": "{{FrontSide}}<hr id='answer'>{{Back}}",
        }],
        css=base_css,
    )


def spec_to_model(spec: dict[str, Any], forced_name: str | None = None) -> genanki.Model | None:
    try:
        fields = [{"name": f["name"]} for f in spec.get("flds", [])]
        templates = []
        for t in spec.get("tmpls", []):
            templates.append({"name": t.get("name", "Card"), "qfmt": t.get("qfmt", ""), "afmt": t.get("afmt", "")})
        if not fields or not templates:
            return None
        return genanki.Model(
            int(spec["id"]),
            forced_name or spec["name"],
            fields=fields,
            templates=templates,
            css=spec.get("css", ""),
            model_type=genanki.Model.CLOZE if int(spec.get("type", 0)) == 1 else genanki.Model.STANDARD,
        )
    except Exception as exc:
        print("Model conversion failed:", spec.get("name"), exc)
        return None


def select_model(kind: str) -> genanki.Model:
    exact_names = {
        "cloze": ["!표준화 cloze ver2.1", "!표준화 Cloze ver2.1"],
        "basic": ["!표준화 Basic ver2.1", "!표준화 basic ver2.1"],
        "exam": ["!표준화 뉴족보 ver2.1", "!표준화 족보 ver2.1"],
    }[kind]
    for exact in exact_names:
        for spec in ALL_MODEL_SPECS:
            if spec.get("name") == exact:
                model = spec_to_model(spec)
                if model:
                    print(f"Using exact template model: {exact}")
                    return model
    # A looser match still preserves the shared template's fields and styling but normalizes the name.
    patterns = {
        "cloze": ("cloze", 1),
        "basic": ("basic", 0),
        "exam": ("족보", 0),
    }
    word, type_value = patterns[kind]
    for spec in ALL_MODEL_SPECS:
        if word.lower() in str(spec.get("name", "")).lower() and int(spec.get("type", 0)) == type_value:
            model = spec_to_model(spec, exact_names[0])
            if model:
                print(f"Using compatible template model {spec.get('name')} as {exact_names[0]}")
                return model
    print(f"No compatible shared model found for {kind}; using a standardized fallback.")
    return fallback_model(kind)


CLOZE_MODEL = select_model("cloze")
BASIC_MODEL = select_model("basic")
EXAM_MODEL = select_model("exam")


def model_field_names(model: genanki.Model) -> list[str]:
    return [f["name"] for f in model.fields]


def fields_for_model(model: genanki.Model, front: str, back: str, *, text: str | None = None, extra: str | None = None) -> list[str]:
    names = model_field_names(model)
    values: list[str] = []
    for name in names:
        key = name.lower().replace("_", " ").strip()
        if "back extra" in key or key in {"extra", "remarks", "remark", "해설", "설명"}:
            values.append(extra if extra is not None else back)
        elif key == "text" or "cloze" in key:
            values.append(text if text is not None else front)
        elif "front" in key or key in {"question", "문제"}:
            values.append(front)
        elif "back" in key or key in {"answer", "정답"}:
            values.append(back)
        else:
            values.append("")
    return values


def img_html(filename: str, alt: str = "") -> str:
    return f'<div class="img-wrap"><img src="{html.escape(filename)}" alt="{html.escape(alt)}"></div>'


def render_crop(pdf_path: Path, page_no: int, norm_rect: tuple[float, float, float, float], filename: str, zoom: float = 2.6) -> Path:
    doc = fitz.open(pdf_path)
    page = doc[page_no - 1]
    r = page.rect
    x0, y0, x1, y1 = norm_rect
    clip = fitz.Rect(r.x0 + r.width * x0, r.y0 + r.height * y0, r.x0 + r.width * x1, r.y0 + r.height * y1)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    out = MEDIA / filename
    pix.save(str(out))
    doc.close()
    return out


def render_rect(page: fitz.Page, rect: fitz.Rect, filename: str, zoom: float = 2.8) -> Path:
    rect = fitz.Rect(max(page.rect.x0, rect.x0), max(page.rect.y0, rect.y0), min(page.rect.x1, rect.x1), min(page.rect.y1, rect.y1))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
    out = MEDIA / filename
    pix.save(str(out))
    return out


def make_collage(images: list[Path], filename: str, captions: list[str] | None = None, columns: int = 2, max_cell_width: int = 760) -> Path:
    valid = [p for p in images if p.exists()]
    if not valid:
        raise ValueError(f"No images for collage {filename}")
    captions = captions or [""] * len(valid)
    font = ImageFont.load_default()
    prepared: list[tuple[Image.Image, str]] = []
    for p, cap in zip(valid, captions):
        im = Image.open(p).convert("RGB")
        if im.width > max_cell_width:
            ratio = max_cell_width / im.width
            im = im.resize((max_cell_width, int(im.height * ratio)), Image.Resampling.LANCZOS)
        prepared.append((im, cap))
    columns = max(1, min(columns, len(prepared)))
    rows = (len(prepared) + columns - 1) // columns
    cell_w = max(im.width for im, _ in prepared) + 30
    cell_h = max(im.height for im, _ in prepared) + 58
    canvas = Image.new("RGB", (cell_w * columns, cell_h * rows), "white")
    draw = ImageDraw.Draw(canvas)
    for idx, (im, cap) in enumerate(prepared):
        row, col = divmod(idx, columns)
        x = col * cell_w + (cell_w - im.width) // 2
        y = row * cell_h + 30
        canvas.paste(im, (x, y))
        if cap:
            draw.text((col * cell_w + 12, row * cell_h + 8), cap, fill="black", font=font)
    out = MEDIA / filename
    canvas.save(out, quality=92)
    return out


def extract_question_media(pdf_path: Path, page_no: int, start_key: str, end_key: str | None, prefix: str) -> Path:
    """Extract image blocks inside an exam question. Falls back to a readable question-panel crop."""
    doc = fitz.open(pdf_path)
    page = doc[page_no - 1]
    start_hits = page.search_for(start_key)
    if start_hits:
        y0 = min(r.y0 for r in start_hits) - 8
    else:
        y0 = page.rect.height * 0.05
    y1 = page.rect.height * 0.96
    if end_key:
        end_hits = [r for r in page.search_for(end_key) if r.y0 > y0]
        if end_hits:
            y1 = min(r.y0 for r in end_hits) - 8
    question_rect = fitz.Rect(page.rect.x0 + 8, max(page.rect.y0, y0), page.rect.x1 - 8, min(page.rect.y1, y1))
    blocks = page.get_text("dict").get("blocks", [])
    image_rects: list[fitz.Rect] = []
    for block in blocks:
        if block.get("type") != 1:
            continue
        rect = fitz.Rect(block["bbox"])
        cy = (rect.y0 + rect.y1) / 2
        if y0 <= cy <= y1 and rect.width >= 45 and rect.height >= 35 and rect.get_area() >= 2500:
            image_rects.append(rect)
    # Deduplicate nearly identical rectangles.
    unique: list[fitz.Rect] = []
    for r in sorted(image_rects, key=lambda z: z.get_area(), reverse=True):
        if not any(abs(r.x0-u.x0)<3 and abs(r.y0-u.y0)<3 and abs(r.x1-u.x1)<3 and abs(r.y1-u.y1)<3 for u in unique):
            unique.append(r)
    unique = sorted(unique[:4], key=lambda z: (z.y0, z.x0))
    pieces: list[Path] = []
    for i, rect in enumerate(unique):
        margin = 5
        rect = fitz.Rect(rect.x0-margin, rect.y0-margin, rect.x1+margin, rect.y1+margin)
        pieces.append(render_rect(page, rect, f"{prefix}_{i+1}.png", zoom=3.0))
    if pieces:
        out = pieces[0] if len(pieces) == 1 else make_collage(pieces, f"{prefix}_combined.png", columns=min(2, len(pieces)))
    else:
        out = render_rect(page, question_rect, f"{prefix}_panel.png", zoom=2.4)
    doc.close()
    return out


# ---------- Crop lecture and exam media ----------
media_files: list[Path] = []

def add_media(path: Path) -> str:
    media_files.append(path)
    return path.name

# Pediatric lecture/summary images.
peds_imgs: dict[str, str] = {}
peds_crop_specs = {
    "warming": (6, (0.50, 0.12, 0.96, 0.52)),
    "tgdc_concept": (7, (0.05, 0.30, 0.95, 0.84)),
    "sistrunk": (8, (0.05, 0.23, 0.96, 0.70)),
    "branchial_types": (9, (0.04, 0.16, 0.48, 0.58)),
    "branchial_photo": (10, (0.03, 0.14, 0.97, 0.52)),
    "lm": (11, (0.02, 0.13, 0.98, 0.48)),
    "nec": (12, (0.02, 0.13, 0.98, 0.49)),
    "nec_tx": (13, (0.03, 0.15, 0.97, 0.82)),
    "red_flags": (14, (0.03, 0.16, 0.97, 0.80)),
    "three_clues": (15, (0.04, 0.15, 0.96, 0.76)),
    "appendix_us": (16, (0.04, 0.16, 0.96, 0.82)),
    "serial_exam": (17, (0.04, 0.14, 0.96, 0.84)),
}
for key, (page, rect) in peds_crop_specs.items():
    peds_imgs[key] = add_media(render_crop(PEDS_PDF, page, rect, f"peds_{key}.png"))

# Pediatric question panels/images.
def peds_half(page: int, top: bool, name: str) -> str:
    rect = (0.02, 0.05, 0.98, 0.51) if top else (0.02, 0.48, 0.98, 0.95)
    return add_media(render_crop(PEDS_PDF, page, rect, f"peds_{name}.png", zoom=2.4))

peds_q = {
    "q1": peds_half(20, True, "q1_kmle50"),
    "q2": peds_half(20, False, "q2_kmle52"),
    "q3": peds_half(21, True, "q3_kmle42"),
    "q4": peds_half(21, False, "q4_kmle46"),
    "q5": add_media(render_crop(PEDS_PDF, 22, (0.02,0.05,0.98,0.83), "peds_q5_kmle43.png", zoom=2.4)),
    "q7": peds_half(23, False, "q7_kmle44"),
    "q8": peds_half(24, True, "q8_kmle45"),
    "q9": peds_half(24, False, "q9_kmle47"),
    "q10": peds_half(25, True, "q10_kmle51"),
    "q11": peds_half(25, False, "q11_kmle48"),
    "q12": peds_half(26, True, "q12_kmle49"),
    "q15": peds_half(27, False, "q15_school_volvulus"),
    "q16": peds_half(28, True, "q16_school_intussusception"),
    "q17": peds_half(28, False, "q17_kmle41"),
    "q18": add_media(render_crop(PEDS_PDF, 29, (0.02,0.05,0.98,0.55), "peds_q18_school_biliary.png", zoom=2.4)),
}
# Recognition galleries for JBL backs.
tgdc_gallery = add_media(make_collage(
    [MEDIA/peds_q[k] for k in ["q3","q7","q8","q9","q10"]],
    "peds_tgdc_kmle_gallery.png",
    ["KMLE 42", "KMLE 44", "KMLE 45", "KMLE 47", "KMLE 51"], columns=2,
))
branchial_gallery = add_media(make_collage(
    [MEDIA/peds_q[k] for k in ["q2","q12"]], "peds_branchial_kmle_gallery.png", ["KMLE 52", "KMLE 49"], columns=2,
))
lm_gallery = add_media(make_collage(
    [MEDIA/peds_q[k] for k in ["q5","q11"]], "peds_lm_kmle_gallery.png", ["KMLE 43", "KMLE 48"], columns=2,
))
acute_gallery = add_media(make_collage(
    [MEDIA/peds_q[k] for k in ["q15","q16","q18"]], "peds_school_abdomen_gallery.png", ["Midgut volvulus", "Intussusception", "Biliary atresia"], columns=2,
))

# Breast lecture images.
breast_imgs: dict[str, str] = {}
breast_crop_specs = {
    "projection": (11, (0.04, 0.14, 0.96, 0.86)),
    "cc_mlo": (13, (0.03, 0.14, 0.97, 0.85)),
    "actual_views": (16, (0.03, 0.14, 0.97, 0.91)),
    "density": (19, (0.02, 0.13, 0.98, 0.86)),
    "calcification": (22, (0.03, 0.14, 0.97, 0.91)),
    "cat5_mammo": (26, (0.03, 0.18, 0.72, 0.92)),
    "cyst_solid": (29, (0.02, 0.16, 0.70, 0.93)),
    "us_malignant": (30, (0.42, 0.14, 0.97, 0.91)),
    "dbt": (33, (0.03, 0.14, 0.97, 0.88)),
    "mri_curve": (38, (0.04, 0.13, 0.96, 0.88)),
    "biopsy": (43, (0.02, 0.13, 0.98, 0.89)),
    "stereotactic": (44, (0.35, 0.14, 0.97, 0.91)),
    "wire": (45, (0.28, 0.13, 0.98, 0.92)),
    "case_mammo": (48, (0.02, 0.13, 0.72, 0.92)),
    "case_us": (49, (0.03, 0.13, 0.96, 0.89)),
    "case_mri": (51, (0.03, 0.13, 0.97, 0.80)),
}
for key, (page, rect) in breast_crop_specs.items():
    breast_imgs[key] = add_media(render_crop(BREAST_PDF, page, rect, f"breast_{key}.png"))

# Every image-bearing Breast Imaging exam question from 2019-2026 is extracted and surfaced in JBL.
breast_exam_specs = {
    "2026_q71_us": (402, "26-연계-71", "26-연계-72"),
    "2026_q72_mammo": (403, "26-연계-72", "26-연계-73"),
    "2023_q94_mammo": (404, "23-연계-94", "2022"),
    "2022_q96_mammo": (405, "22-연계강좌-96", "22-연계강좌-97"),
    "2022_q97_implant": (405, "22-연계강좌-97", "2021"),
    "2021_q93_mammo": (406, "21-연계강좌-93", "21-연계강좌-94"),
    "2021_q94_implant": (406, "21-연계강좌-94", "2020"),
    "2019_q63_mammo": (407, "19-연계-63", "19-연계-64"),
    "2019_q64_wire": (408, "19-연계-64", None),
}
breast_exam_imgs: dict[str, str] = {}
for key, (page, start, end) in breast_exam_specs.items():
    path = extract_question_media(EXAM_PDF, page, start, end, f"breast_exam_{key}")
    breast_exam_imgs[key] = add_media(path)

mammo_exam_gallery = add_media(make_collage(
    [MEDIA/breast_exam_imgs[k] for k in ["2026_q72_mammo","2023_q94_mammo","2022_q96_mammo","2021_q93_mammo","2019_q63_mammo"]],
    "breast_exam_mammography_gallery.png",
    ["2026 Q72", "2023 Q94", "2022 Q96", "2021 Q93", "2019 Q63"],
    columns=2,
))
implant_exam_gallery = add_media(make_collage(
    [MEDIA/breast_exam_imgs[k] for k in ["2022_q97_implant","2021_q94_implant"]],
    "breast_exam_implant_gallery.png", ["2022 Q97", "2021 Q94"], columns=2,
))


# ---------- Note/deck helpers ----------
class StableNote(genanki.Note):
    @property
    def guid(self) -> str:
        return genanki.guid_for(self.model.name, *self.fields)


def add_cloze(deck: genanki.Deck, text: str, extra: str) -> None:
    deck.add_note(StableNote(model=CLOZE_MODEL, fields=fields_for_model(CLOZE_MODEL, text, extra, text=text, extra=extra), tags=[]))


def add_basic(deck: genanki.Deck, front: str, back: str) -> None:
    deck.add_note(StableNote(model=BASIC_MODEL, fields=fields_for_model(BASIC_MODEL, front, back), tags=[]))


def add_exam(deck: genanki.Deck, front: str, back: str) -> None:
    deck.add_note(StableNote(model=EXAM_MODEL, fields=fields_for_model(EXAM_MODEL, front, back), tags=[]))


def exam_back(answer: str, explanation: str, options: list[tuple[str, str]] | None = None, takeaway: str | None = None) -> str:
    chunks = [f"<b>정답: {answer}</b>", f"<div class='good'>{explanation}</div>"]
    if options:
        chunks.append("<br><b>선지별 해설</b><br>" + "<br>".join(f"{html.escape(label)} {text}" for label, text in options))
    if takeaway:
        chunks.append(f"<div class='warn'><b>가져갈 한 줄</b><br>{takeaway}</div>")
    return "".join(chunks)


# ---------- Pediatric Surgery deck ----------
peds_root = "외과학 입문::3. 계통별 수술::소아외과 (소화기학) (박태진) by 이용화"
peds_jbl = genanki.Deck(deterministic_id(peds_root+"::1. JBL"), peds_root+"::1. JBL")
peds_ref = genanki.Deck(deterministic_id(peds_root+"::2. 참공"), peds_root+"::2. 참공")
peds_school = genanki.Deck(deterministic_id(peds_root+"::3. 족보"), peds_root+"::3. 족보")
peds_kmle = genanki.Deck(deterministic_id(peds_root+"::4. KMLE"), peds_root+"::4. KMLE")

add_cloze(peds_jbl,
    "<b>신생아 수술 환자의 기본 개념</b><br><br>신생아는 혈액량이 적고 장기 예비력이 낮으며 열과 수분을 쉽게 잃습니다. 따라서 신생아 수술에서는 수술 술기뿐 아니라 이송부터 시작되는 {{c1::보온과 수액 관리}}가 치료의 일부입니다.",
    "소량의 출혈이나 작은 계산 오차도 전체 혈액량에서 큰 비율을 차지합니다. 체표면적에 비해 체중이 작고 피하지방과 체온 조절 능력이 부족해 이동 중에도 쉽게 저체온이 됩니다." + img_html(peds_imgs["warming"], "신생아 보온") + "<div class='exam-label'>KMLE의 복벽갈림증 문제도 질환명보다 노출된 장에서 생기는 열·수분 손실에 대한 초기 대응을 묻습니다.</div>" + img_html(peds_q["q17"], "KMLE 신생아 관리 응용")
)
add_cloze(peds_jbl,
    "<b>신생아에서 저체온이 위험한 이유</b><br><br>신생아의 체온이 떨어지면 대사와 산소 소모가 증가하고, 상태가 악화되면 {{c1::대사성 산증}}과 응고장애, 서맥으로 이어질 수 있습니다.",
    "보온은 수술실에 도착한 뒤 시작하는 처치가 아닙니다. 수술실 온도, heat lamp, 가온 장비, 따뜻한 세척액과 소독액을 이용해 이송 전부터 열 손실을 줄입니다."
)
add_cloze(peds_jbl,
    "<b>소아 경부 종물의 출발점</b><br><br>소아 경부 종물은 질환명을 바로 맞히기보다 먼저 {{c1::정중과 측방}}으로 나눕니다. 정중 종물은 혀나 연하에 따라 움직이는지, 측방 종물은 반복되는 분비·감염이나 퍼지는 낭성 형태가 있는지 확인합니다.",
    "정중에서는 갑상설관낭종, 표피·유피낭종, 이소성 갑상선을 생각합니다. 측방에서는 새열기형, 림프관기형, 림프절염을 생각합니다. 접근 순서는 위치 → 움직임 → 감염/분비 → 영상 → 치료입니다."
)
add_cloze(peds_jbl,
    "<b>갑상설관낭종</b><br><br>갑상설관낭종은 갑상선이 혀뿌리에서 내려온 뒤 통로가 남아 생기는 선천성 병변입니다. 따라서 혀를 내밀거나 삼킬 때 움직이는 정중 경부 종물은 {{c1::갑상설관낭종}}을 우선 생각합니다.",
    img_html(peds_imgs["tgdc_concept"], "갑상설관낭종 개념") + "잔존 tract가 혀뿌리와 설골 주변에 이어져 있어 혀와 함께 움직입니다. 아래는 같은 단서를 반복해서 물은 실제 KMLE 영상들입니다." + img_html(tgdc_gallery, "TGDC KMLE 영상 모음")
)
add_cloze(peds_jbl,
    "<b>갑상설관낭종의 치료</b><br><br>갑상설관낭종의 근치 치료는 {{c1::Sistrunk 수술}}입니다. 수술 전에는 정상 위치에 기능하는 갑상선이 있는지도 확인합니다.",
    "낭종만 제거하면 미세 tract가 남아 재발할 수 있습니다. Sistrunk 수술은 낭종과 잔존 tract, 설골 중앙부를 함께 제거합니다. 급성 감염기에는 먼저 항생제와 필요한 배액으로 염증을 가라앉힌 뒤 수술합니다." + img_html(peds_imgs["sistrunk"], "Sistrunk 수술 원리") + img_html(peds_q["q1"], "KMLE Sistrunk 문제")
)
add_cloze(peds_jbl,
    "<b>제2 새열기형</b><br><br>흉쇄유돌근 앞쪽 아래에 작은 구멍이 있고 같은 위치에서 분비나 감염이 반복된다면 {{c1::제2 새열기형}}을 생각합니다. 근치 치료는 tract의 {{c2::전장 절제}}입니다.",
    "농양만 배농하면 tract가 남아 감염이 반복됩니다. 급성 감염을 먼저 치료한 뒤, 감염이 가라앉은 시기에 tract 전체를 추적해 제거합니다." + img_html(peds_imgs["branchial_photo"], "제2 새열기형") + img_html(branchial_gallery, "새열기형 KMLE 영상 모음")
)
add_cloze(peds_jbl,
    "<b>림프관기형</b><br><br>림프관기형은 림프계 발달 이상으로 림프액이 고여 생기는 선천성 병변입니다. 목이나 액와부의 부드러운 다방성 낭성 종괴가 신경과 혈관을 감싸며 퍼져 있다면 {{c1::림프관기형}}을 생각합니다.",
    "국소적이고 완전 절제가 가능하면 수술할 수 있지만, 중요 구조물 사이로 광범위하게 퍼지면 무리한 절제보다 경화요법을 우선 고려합니다. 감염이나 낭내 출혈로 갑자기 커져 기도를 압박하면 응급상황입니다." + img_html(peds_imgs["lm"], "림프관기형") + img_html(lm_gallery, "림프관기형 KMLE 영상 모음")
)
add_cloze(peds_jbl,
    "<b>괴사성 장염의 외과적 판단</b><br><br>괴사성 장염은 주로 조산아와 극소저체중아에서 발생하며, 장이 괴사하면서 복부 팽만이나 복벽의 색 변화가 나타날 수 있습니다. 복강 내 free air는 장천공을 의미하므로 {{c1::수술}}이 필요합니다.",
    "Free air는 절대적 수술 적응증입니다. 반복 영상에서 같은 위치에 남는 fixed bowel loop, 진행하는 복부팽만, 내과 치료에도 악화되는 상태는 상대적 수술 적응증입니다." + img_html(peds_imgs["nec"], "NEC 임상 소견")
)
add_cloze(peds_jbl,
    "<b>천공이 없는 NEC의 치료</b><br><br>장천공이 없고 환아가 안정적이라면 금식, 위장관 감압, 정맥영양과 광범위 항생제를 포함한 {{c1::내과적 치료}}로 장을 먼저 쉬게 합니다.",
    "수술에서는 살아날 가능성이 있는 장을 최대한 보존해야 합니다. 경계가 애매한 장을 모두 절제하면 short bowel이 생길 수 있어 second-look을 이용할 수 있습니다." + img_html(peds_imgs["nec_tx"], "NEC 치료와 수술")
)
add_cloze(peds_jbl,
    "<b>소아 급성 복통의 목표</b><br><br>소아 급성 복통에서는 모든 질환을 외우는 것보다 수술이 필요한 아이를 놓치지 않는 것이 중요합니다. 아이가 통증 때문에 잠에서 깨거나 담즙성 구토가 동반되면 {{c1::외과 평가와 재평가}}를 적극 고려합니다.",
    "섭취 거부, 혈변, 고환 통증이나 부종, 체중 감소도 red flag입니다. 한 번의 진찰이나 음성 영상으로 끝내지 않고 시간에 따른 경과를 봅니다." + img_html(peds_imgs["red_flags"], "소아 복통 red flags")
)
add_cloze(peds_jbl,
    "<b>급성 복통의 대표 단서</b><br><br>배꼽 주위 통증이 오른쪽 아랫배로 이동하면 {{c1::충수염}}, 주기적 복통과 혈성 점액변은 {{c2::장중첩증}}, 담즙성 구토는 {{c3::중장염전}}을 생각합니다.",
    "강의에서는 세부 술기보다 병력에서 이 단서를 먼저 잡는 수준을 강조했습니다. 학교 족보에서 같은 단서가 실제 영상과 함께 반복되었습니다." + img_html(peds_imgs["three_clues"], "세 가지 단서") + img_html(acute_gallery, "학교 족보 관련 영상")
)
add_cloze(peds_jbl,
    "<b>소아 충수염을 놓치지 않는 법</b><br><br>어린아이의 충수염은 설사, 구토, 발열과 보챔만 보여 장염처럼 보일 수 있습니다. 초음파가 불명확하더라도 임상적 의심이 남는다면 {{c1::반복 진찰과 추적 평가}}가 필요합니다.",
    "Appendix not visualized는 정상 충수라는 뜻이 아니라 평가가 제한되었다는 의미입니다. 필요한 경우 추적 초음파나 CT를 시행하고, 증상이 지속되는데 영상이 반복해서 애매하면 진단적 복강경도 고려할 수 있습니다." + img_html(peds_imgs["appendix_us"], "제한된 충수 초음파") + img_html(peds_imgs["serial_exam"], "반복 진찰과 영상")
)

# Pediatric reference cards: one-step extensions only.
add_basic(peds_ref,
    "<b>새열기형의 형태</b><br><br>cyst, sinus, fistula는 어떻게 구분합니까?",
    "개구부 수로 구분합니다.<br><br><b>Cyst</b>: 외부와 연결되지 않은 폐쇄 공간, 개구부 0개<br><b>Sinus</b>: 피부 또는 인두 한쪽으로만 열린 통로, 1개<br><b>Fistula</b>: 피부와 인두를 연결하는 통로, 2개" + img_html(peds_imgs["branchial_types"], "새열기형 형태")
)
add_basic(peds_ref,
    "<b>림프관기형의 형태와 치료 확장</b><br><br>Macrocystic과 microcystic 병변은 치료 접근성이 어떻게 다릅니까?",
    "Macrocystic 병변은 큰 낭이 있어 천자와 경화요법에 비교적 접근하기 쉽습니다. Microcystic 병변은 작은 낭이 조직 사이로 퍼져 완전 절제와 천자가 어렵고 잔존·재발이 문제가 됩니다. 광범위 microcystic 병변에서는 sirolimus가 언급되었습니다."
)
add_basic(peds_ref,
    "<b>NEC와 SIP</b><br><br>전신 상태가 비교적 괜찮은데 국소 장천공이 생겼다면 무엇을 생각합니까?",
    "Spontaneous intestinal perforation(SIP)을 NEC와 구분해 생각합니다. 질환은 다르지만 장천공이 확인되면 둘 다 외과적 처치가 필요합니다. 신생아는 세워 촬영하기 어려워 supine 또는 lateral decubitus film에서 free air를 확인합니다."
)
add_basic(peds_ref,
    "<b>NEC에서 장을 보존하는 전략</b><br><br>Second-look과 일차 복막배액은 언제 고려합니까?",
    "장의 생존 여부가 불분명하면 24–48시간 뒤 second-look으로 다시 평가해 불필요한 광범위 절제를 피합니다. 개복을 견디기 어려운 극소저체중·불안정 환아에서는 먼저 복막배액으로 오염을 줄이고 상태가 호전된 뒤 수술할 수 있습니다."
)
add_basic(peds_ref,
    "<b>연관 문제의 변주 단서</b><br><br>강의 핵심에서 한 단계 확장해 기억할 단서는 무엇입니까?",
    "최근 상기도 감염 뒤 생긴 소아의 작은 림프절은 반응성일 가능성이 높습니다. 장중첩증은 ileocolic type이 가장 흔합니다. 영아의 황달과 회색 변은 담도폐쇄증을 의심하는 red flag입니다. 이 질환들의 세부 치료는 이번 강의의 직접 범위는 아닙니다."
)

# Pediatric school exam cards.
add_exam(peds_school,
    "<b>2009 연계 주관식</b><br><br>소아에서 흔하게 나타나는 cervical anomalies를 4가지 이상 기술하시오.",
    exam_back("주관식", "현재 강의에서 직접 연결되는 범주는 갑상설관낭종, 새열기형, 림프관기형, 유피낭종입니다.", takeaway="정중/측방 위치와 각 질환의 대표 치료까지 함께 연결합니다.")
)
add_exam(peds_school,
    "<b>2013 연계-59</b><br><br>경부 종물이 있을 때 악성보다 양성을 의심할 수 있는 환자는?<br>① 7일 전 상기도 감염 치료를 받은 9세 남아, 1 cm 림프절<br>② 20년 이상 흡연한 남자, 5 cm 경부 종물<br>③ 40세 남자, 4 cm 쇄골상부 림프절<br>④ 안면신경마비가 동반된 이하선 종물<br>⑤ 방사선치료 병력이 있는 환자의 갑상선 종물",
    exam_back("①", "최근 상기도 감염 뒤 생긴 소아의 작은 림프절은 반응성·염증성일 가능성이 높습니다.", takeaway="소아의 작은 감염 후 림프절과 성인의 악성 위험 단서를 구분합니다.")
)
add_exam(peds_school,
    "<b>2010 연계-62</b><br><br>경부종물에 대한 설명으로 맞는 것은?<br>① 경부종물에서 종양은 20%에 불과하다.<br>② 성인에서는 염증성 병변이 더 흔하다.<br>③ 성인에서는 담배와 술이 알려진 위험인자다.<br>④ 소아는 악성이 더 흔하다.<br>⑤ 쇄골상부 림프절은 주로 두경부 종양 전이다.",
    exam_back("③", "성인의 경부종물에서는 흡연과 음주가 중요한 악성 위험인자입니다.", takeaway="소아에서는 발생성·염증성 병변을 먼저 생각하고, 성인에서는 악성을 우선 배제합니다.")
)
add_exam(peds_school,
    "<b>2011 소화기학 2차-95</b><br><br>구토를 주소로 내원한 환아의 감별질환 중 가장 응급으로 수술해야 하는 경우는?<br>① Annular pancreas<br>② Duodenal web<br>③ Duodenal atresia<br>④ Midgut volvulus<br>⑤ Malrotation" + img_html(peds_q["q15"], "중장염전 족보"),
    exam_back("④", "Midgut volvulus는 장 혈류가 차단될 수 있어 제시된 질환 중 가장 응급입니다.", takeaway="소아의 담즙성 구토는 중장염전을 먼저 배제합니다.")
)
add_exam(peds_school,
    "<b>2011 소화기학 2차-96</b><br><br>생후 6개월 환아가 주기적으로 자지러지는 복통과 혈성 점액변을 보이며, 증상이 없을 때는 잘 논다. 옳은 설명은?<br>① 단순복부촬영으로 쉽게 진단한다.<br>② 공기정복술은 잘 시행하지 않는다.<br>③ 말단회장과 맹장 사이에서 발병하는 형태가 가장 흔하다.<br>④ 수술적 도수정복 뒤 재발이 흔하다.<br>⑤ 즉시 개복한다." + img_html(peds_q["q16"], "장중첩증 족보"),
    exam_back("③", "주기적 복통, 증상 사이 정상, 혈성 점액변은 장중첩증이며 ileocolic type이 가장 흔합니다.", takeaway="강의 직접 핵심은 혈성 점액변으로 장중첩증을 알아보는 것입니다.")
)
add_exam(peds_school,
    "<b>2024 소화기학 1차-8</b><br><br>50일 여아가 황달과 회색 대변을 보이고, 초음파에서 담낭이 매우 작으며 총담관이 보이지 않는다. 진단은?<br>① Acute cholecystitis<br>② Biliary atresia<br>③ Pancreatic pseudocyst<br>④ Choledochal cyst<br>⑤ Portal vein thrombosis" + img_html(peds_q["q18"], "담도폐쇄증 족보"),
    exam_back("②", "황달과 회색 변, 작은 담낭과 보이지 않는 총담관은 담도폐쇄증을 시사합니다.", takeaway="담도폐쇄증 치료는 강의 범위 밖이고, 이 문제는 red flag 적용용입니다.")
)

# Pediatric KMLE cards with source images.
kmle_cards = [
    ("KMLE 소아외과 50", peds_q["q1"], "갑상설관낭종 수술에서 설골 중앙부를 함께 절제하는 수술은?", "④ Sistrunk 수술", "미세 tract가 설골을 지나므로 낭종과 설골 중앙부를 함께 제거합니다."),
    ("KMLE 소아외과 52", peds_q["q2"], "SCM 앞쪽 하부 1/3의 작은 구멍과 반복 분비를 보이는 7개월 남아의 진단은?", "② 제2 새열기형", "위치와 외부 개구부, 반복 분비가 핵심입니다."),
    ("KMLE 소아외과 42", peds_q["q3"], "혀를 내밀 때 위로 움직이는 정중 경부 종물의 진단은?", "② 갑상설관낭종", "정중 위치와 혀 움직임은 대표 단서입니다."),
    ("KMLE 소아외과 46", peds_q["q4"], "높은 정중 경부 종물과 TSH 상승이 있을 때 필요한 검사는?", "⑤ 갑상선 스캔", "정상 위치 갑상선과 유일한 기능성 이소성 갑상선을 확인합니다."),
    ("KMLE 소아외과 43", peds_q["q5"], "영아의 크고 부드러운 다방성 낭성 경부 종괴의 진단은?", "③ 림프관기형", "Cystic hygroma는 현재 lymphatic malformation으로 부릅니다."),
    ("KMLE 소아외과 44", peds_q["q7"], "정중 경부 종물이 혀 움직임에 따라 이동한다. 진단은?", "④ 갑상설관낭종", "같은 왕족 단서의 반복입니다."),
    ("KMLE 소아외과 45", peds_q["q8"], "3세의 정중 경부 종물이 혀를 내밀 때 움직인다. 진단은?", "④ 갑상설관낭종", "같은 왕족 단서의 반복입니다."),
    ("KMLE 소아외과 47", peds_q["q9"], "5세의 정중 1 cm 종물이 혀를 내밀 때 움직인다. 진단은?", "④ 갑상설관낭종", "같은 왕족 단서의 반복입니다."),
    ("KMLE 소아외과 51", peds_q["q10"], "턱 아래 정중 종물이 연하·혀 움직임과 함께 이동하고 CT에서 낭성 병변이다. 진단은?", "② 갑상설관낭종", "위치, 움직임, 낭성 영상이 모두 맞습니다."),
    ("KMLE 소아외과 48", peds_q["q11"], "출생 직후부터 있던 posterior neck cystic mass의 진단은?", "① Cystic hygroma", "Posterior neck의 선천성 낭성 종괴는 LM에 합당합니다."),
    ("KMLE 소아외과 49", peds_q["q12"], "측경부의 말랑한 종물의 진단은?", "① Branchial cleft cyst", "측경부 위치와 낭성 성상이 핵심입니다."),
    ("KMLE 소아외과 41", peds_q["q17"], "노출된 장을 보이는 신생아의 초기 처치로 옳은 것은?", "③ 보온과 충분한 수액 공급", "노출된 장에서 열과 수분 손실이 크므로 체온 유지와 수액 공급이 우선입니다."),
]
for title, image, question, answer, explanation in kmle_cards:
    add_exam(peds_kmle, f"<b>{title}</b><br><br>{question}" + img_html(image, title), exam_back(answer, explanation))


# ---------- Breast Imaging JBL-only deck ----------
breast_root = "외과학 입문::3. 계통별 수술::유방영상학 1, 2 (최혜영) by 이용화"
breast_jbl = genanki.Deck(deterministic_id(breast_root+"::1. JBL"), breast_root+"::1. JBL")

add_cloze(breast_jbl,
    "<b>유방 영상검사의 전체 지도</b><br><br>유방 영상검사는 서로 대체하지 않고 목적에 따라 보완합니다.<br><br>{{c1::유방촬영술}}은 기본 검사이자 미세석회화 평가에 가장 유용하고, {{c2::초음파}}는 낭성/고형 감별과 치밀유방의 촉지 종괴 평가에 유용하며, {{c3::MRI}}는 가장 민감한 검사로 암의 범위와 다발성을 평가합니다.",
    "유방촬영술은 저에너지 X-ray를 사용합니다. 초음파는 실시간으로 병변을 보고 조직검사를 유도할 수 있습니다. MRI는 특이도가 낮아 조직검사를 대체하지 못합니다.<div class='exam-label'>2019–2026년 족보에서 검사법별 장단점이 거의 매년 선지만 바뀌어 반복되었습니다.</div>"
)
add_cloze(breast_jbl,
    "<b>유방암 국가검진</b><br><br>40–69세 무증상 여성에게 유방암 사망률 감소가 입증된 검사는 {{c1::유방촬영술}}이며, {{c2::2년마다}} 시행합니다.",
    "일상적 유방초음파 단독 또는 병행 검진은 근거가 충분하지 않습니다. BRCA 변이, 흉부 방사선 조사력 등 고위험군은 별도의 MRI 검진 권고를 따릅니다. 이 문장은 2019~2022년에 반복 출제된 왕족입니다."
)
add_cloze(breast_jbl,
    "<b>Mammography의 원리</b><br><br>유방촬영술은 3차원 유방을 2차원으로 압축해 보는 {{c1::투영 영상}}입니다. 정상 조직의 겹침이 병변을 가릴 수 있으며 이 문제는 치밀유방에서 더 심합니다.",
    "두 방향을 촬영하고 유방을 압박하는 이유가 모두 여기서 나옵니다. 압박은 조직 겹침과 움직임, 선량을 줄이고 대비를 높입니다. DBT는 이 겹침을 줄이기 위해 개발되었습니다." + img_html(breast_imgs["projection"], "유방촬영술 투영 원리")
)
add_cloze(breast_jbl,
    "<b>CC와 MLO view</b><br><br>표준 유방촬영술은 양측 {{c1::CC와 MLO}} view로 구성됩니다. 판독은 좌우 대칭을 비교하면서 시작합니다.",
    "CC는 위에서 아래로 촬영해 내측 조직을 포함합니다. MLO는 약 45도로 촬영해 액와부와 유방하부주름까지 가장 많은 조직을 포함하며, 대흉근이 유두 높이까지 내려오면 좋은 영상입니다." + img_html(breast_imgs["cc_mlo"], "CC와 MLO 촬영") + img_html(breast_imgs["actual_views"], "실제 CC와 MLO")
)
add_cloze(breast_jbl,
    "<b>유방 밀도</b><br><br>치밀유방에서는 암도 정상 유선조직도 희게 보여 유방촬영술의 {{c1::민감도가 감소}}합니다. 치밀유방 자체도 유방암의 {{c2::독립적 위험인자}}입니다.",
    "BI-RADS 밀도는 a 거의 대부분 지방, b 산재된 섬유선조직, c 불균등하게 치밀, d 매우 치밀로 기술합니다. 네 유형을 따로 원자화하지 않고 한 그림에서 방향을 익힙니다." + img_html(breast_imgs["density"], "유방 밀도 a-d")
)
add_cloze(breast_jbl,
    "<b>Mammography에서 악성 종괴</b><br><br>유방촬영술에서 불규칙한 모양의 고밀도 종괴에 {{c1::spiculated margin}}이 보이면 악성을 강하게 의심합니다.",
    "대표 악성 조합은 irregular shape + spiculated margin + high density입니다. 반대로 oval + circumscribed는 섬유선종과 같은 양성 병변에 더 가깝습니다." + img_html(breast_imgs["cat5_mammo"], "강의 Category 5 종괴") + "<div class='exam-label'>아래는 실제로 출제된 모든 mammography 이미지 문제입니다. 연도는 달라도 '악성 소견 → 초음파 → 조직검사'라는 판단을 반복합니다.</div>" + img_html(mammo_exam_gallery, "2019-2026 mammography 족보 이미지")
)
add_cloze(breast_jbl,
    "<b>유방촬영술의 미세석회화</b><br><br>석회화는 {{c1::형태와 분포}}를 함께 보고 악성 가능성을 판단합니다. 특히 {{c2::fine linear 또는 fine linear branching}} 형태는 악성을 강하게 시사합니다.",
    "형태는 amorphous → coarse heterogeneous → fine pleomorphic → fine linear/branching으로 갈수록 악성 가능성이 높습니다. 분포는 diffuse보다 linear·segmental이 더 의심스럽습니다. DCIS를 발견하는 핵심 단서이며 미세석회화는 mammography가 가장 잘 봅니다." + img_html(breast_imgs["calcification"], "석회화 형태와 분포")
)
add_cloze(breast_jbl,
    "<b>BI-RADS는 처치까지 포함한다</b><br><br>BI-RADS Category 3은 {{c1::6개월 단기 추적}}, Category 4와 5는 {{c2::조직검사}}로 연결됩니다.",
    "Category 0은 추가 검사 필요, 1은 음성, 2는 양성, 3은 악성 가능성 2% 이하, 4는 의심, 5는 악성 가능성 95% 이상, 6은 조직학적으로 확진된 암입니다. 기억할 경계는 2%와 95%입니다."
)
add_cloze(breast_jbl,
    "<b>초음파에서 단순 낭종</b><br><br>무에코이고 벽이 얇고 매끈하며 후방 음향증강이 보이는 병변은 {{c1::단순 낭종}}이며 BI-RADS Category 2입니다.",
    "초음파는 mammography가 할 수 없는 낭성/고형 감별을 확실히 해줍니다. 고형 종괴는 내부 에코가 있고 모양·방향·경계를 추가로 평가합니다." + img_html(breast_imgs["cyst_solid"], "단순 낭종과 고형 종괴")
)
add_cloze(breast_jbl,
    "<b>초음파에서 악성 종괴</b><br><br>불규칙한 고형 종괴가 세로로 서는 non-parallel orientation을 보이고 경계가 불분명하거나 뒤에 shadowing이 생기면 {{c1::악성}}을 의심합니다. Category 4 이상이면 {{c2::조직검사}}가 필요합니다.",
    "악성 소견은 irregular shape, non-parallel(taller-than-wide), non-circumscribed margin, posterior shadowing입니다. 반대로 타원형, 수평 방향, 경계가 분명하면 섬유선종의 전형입니다." + img_html(breast_imgs["us_malignant"], "초음파 악성 소견") + "<div class='exam-label'>2026 Q71은 강의 마지막 증례와 같은 악성 고형 종괴를 보여주고 Category 4C + 초음파 유도 core biopsy를 답으로 요구했습니다.</div>" + img_html(breast_exam_imgs["2026_q71_us"], "2026 초음파 족보 이미지") + img_html(breast_imgs["case_us"], "강의 통합 증례 초음파")
)
add_cloze(breast_jbl,
    "<b>Digital Breast Tomosynthesis</b><br><br>DBT는 2D mammography의 {{c1::조직 겹침}}을 줄이기 위해 여러 각도에서 촬영한 단층 영상을 재구성합니다.",
    "중첩 음영에 의한 위양성을 줄이고 치밀유방에서 특히 유용합니다. 단점은 데이터량과 판독시간 증가입니다. 2019~2020 족보에서 직접 반복되었습니다." + img_html(breast_imgs["dbt"], "DBT")
)
add_cloze(breast_jbl,
    "<b>Breast MRI의 역할</b><br><br>Breast MRI는 유방영상 중 {{c1::민감도가 가장 높은}} 검사이지만 특이도가 낮아 {{c2::조직검사를 대체하지 못합니다}}.",
    "수술 전 병변의 범위·다발성·반대측 병변 평가, 항암치료 반응, 원발불명 액와 전이, 애매한 병변, 재발, 보형물, 고위험군 검진에 사용합니다. 2026 Q73의 정답도 수술 전 범위와 다발성 평가였습니다." + img_html(breast_imgs["case_mri"], "수술 전 MRI 범위 평가")
)
add_cloze(breast_jbl,
    "<b>MRI 조영증강 곡선</b><br><br>빠르게 조영된 뒤 신호가 감소하는 {{c1::Type III washout}} pattern은 악성을 시사합니다.",
    "Type I persistent는 양성 쪽, Type II plateau는 중간, Type III washout은 악성 쪽입니다. 곡선만으로 진단하지 않고 형태 소견과 함께 BI-RADS를 정합니다." + img_html(breast_imgs["mri_curve"], "MRI 조영증강 곡선")
)
add_cloze(breast_jbl,
    "<b>병변에 맞는 조직검사 유도법</b><br><br>초음파에서 보이는 병변은 {{c1::초음파 유도 생검}}, 초음파에서는 안 보이고 mammography에서만 보이는 미세석회화는 {{c2::입체정위 생검}}으로 접근합니다.",
    "Core needle biopsy는 가장 널리 쓰이는 확진법입니다. Vacuum-assisted biopsy는 한 번 삽입해 더 많은 조직을 연속 채취하며 작은 양성 병변은 제거까지 가능할 수 있습니다." + img_html(breast_imgs["biopsy"], "Core와 vacuum-assisted biopsy") + img_html(breast_imgs["stereotactic"], "Stereotactic biopsy")
)
add_cloze(breast_jbl,
    "<b>수술 전 침 위치 결정술</b><br><br>만져지지 않는 병변을 수술장에서 찾도록 병변에 hook wire를 넣어 표시하는 시술은 {{c1::wire localization}}입니다.",
    "초음파에서 보이는 병변은 초음파 유도, 미세석회화처럼 mammography에서만 보이는 병변은 mammography 유도로 시행합니다. 2019 Q64는 강의 사진 그대로 시술명을 물었습니다." + img_html(breast_imgs["wire"], "강의 wire localization") + img_html(breast_exam_imgs["2019_q64_wire"], "2019 wire localization 족보")
)
add_cloze(breast_jbl,
    "<b>유방 보형물 환자에서 MRI</b><br><br>유방 확대수술을 받은 환자에서 보형물과 주변 유방을 평가하는 데 가장 유용한 검사는 {{c1::MRI}}입니다.",
    "2021과 2022에 같은 강의 이미지가 반복 출제되었습니다. 이 족보의 핵심은 보형물이 있는 환자에서 MRI가 유용하다는 것입니다." + img_html(implant_exam_gallery, "보형물 관련 실제 족보 이미지")
)
add_cloze(breast_jbl,
    "<b>통합 증례의 판독 흐름</b><br><br>촉지 종괴가 mammography에서 불명확한 고밀도 종괴로 보이면 초음파로 내부 성상과 형태를 확인하고, 의심 소견이면 {{c1::core needle biopsy}}로 확진한 뒤, 암이 확인되면 MRI로 {{c2::수술 전 범위}}를 평가합니다.",
    "강의 마지막 증례의 흐름입니다. Mammography → US/BI-RADS 4C → core biopsy → 암 확진 → MRI extent evaluation을 하나의 판단 사슬로 익힙니다." + img_html(breast_imgs["case_mammo"], "통합 증례 mammography") + img_html(breast_imgs["case_us"], "통합 증례 ultrasound") + img_html(breast_imgs["case_mri"], "통합 증례 MRI")
)


# ---------- Export ----------
def export_package(decks: list[genanki.Deck], filename: str) -> Path:
    path = OUT / filename
    pkg = genanki.Package(decks)
    pkg.media_files = [str(p) for p in dict.fromkeys(media_files)]
    pkg.write_to_file(str(path))
    print(f"Wrote {path} ({path.stat().st_size:,} bytes)")
    return path

peds_out = export_package(
    [peds_jbl, peds_ref, peds_school, peds_kmle],
    "외과학 입문__3. 계통별 수술__소아외과 (소화기학) (박태진) by 이용화 0826_개선판.apkg",
)
breast_out = export_package(
    [breast_jbl],
    "외과학 입문__3. 계통별 수술__유방영상학 1, 2 (최혜영) by 이용화 0826.apkg",
)

report = OUT / "BUILD_REPORT.md"
report.write_text(textwrap.dedent(f"""
# Build report

- Pediatric Surgery: `{peds_out.name}`
  - 1. JBL: {len(peds_jbl.notes)} notes
  - 2. 참공: {len(peds_ref.notes)} notes
  - 3. 족보: {len(peds_school.notes)} notes
  - 4. KMLE: {len(peds_kmle.notes)} notes
- Breast Imaging: `{breast_out.name}`
  - 1. JBL: {len(breast_jbl.notes)} notes

## Standardized note types

- Cloze: `{CLOZE_MODEL.name}` / fields: {model_field_names(CLOZE_MODEL)}
- Basic: `{BASIC_MODEL.name}` / fields: {model_field_names(BASIC_MODEL)}
- Exam: `{EXAM_MODEL.name}` / fields: {model_field_names(EXAM_MODEL)}

## Media coverage

- Pediatric: lecture images, school-exam images, and all selected KMLE images are embedded.
- Breast imaging: all image-bearing exam questions from 2019–2026 are surfaced inside the JBL learning sequence.
- Tags: none.
"""), encoding="utf-8")
print(report.read_text(encoding="utf-8"))
