#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import shutil
import sqlite3
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import tools.final_rebuild as source

SEP = "\x1f"
ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "work_inputs"
OUTPUT = ROOT / "outputs_v2"
OUTPUT.mkdir(exist_ok=True)

GYNE_SRC = INPUT / "gyne_source.apkg"
INF_SRC = INPUT / "infertility_source.apkg"
STYLE_MD = INPUT / "concept_style_reference.md"
GYNE_OUT = OUTPUT / "산부인과_영상진단_최종본_개념선행_족보통합.apkg"
INF_OUT = OUTPUT / "난임_Infertility_최종본_개념선행_족보통합.apkg"
REPORT_OUT = OUTPUT / "두_덱_개념선행_최종검증.txt"


def unicase(a, b):
    a = (a or "").casefold()
    b = (b or "").casefold()
    return (a > b) - (a < b)


def strip_html(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>", " ", value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def checksum(value: str) -> int:
    return int(hashlib.sha1(strip_html(value).encode("utf-8")).hexdigest()[:8], 16)


def clean_symbols(value: str) -> str:
    if not value:
        return value
    replacements = {
        "•": "<br>",
        "·": ", ",
        "→": ": ",
        "⇒": ": ",
        "⇢": ": ",
        "↔": "와 ",
        "✓": "",
        "✔": "",
        "▶": "",
        "▷": "",
        "※": "",
        "♘": "",
        "&nbsp;": " ",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"[🫶😂🤣]+", "", value)
    value = re.sub(r"(?i)(<br>\s*){3,}", "<br><br>", value)
    value = re.sub(r"\s+([,.:;])", r"\1", value)
    return value.strip()


def clean_explanation(value: str) -> str:
    value = clean_symbols(value or "")
    lines = re.split(r"(?i)<br\s*/?>|\n", value)
    drop = [
        "죄송", "화이팅", "힘내", "ㅋㅋ", "ㅠㅠ", "학편위", "지나가는 사람",
        "정확한 복원", "복원을 못", "복원이", "토스를 켜", "종강", "개인적으로",
        "족보를 맹신", "내용출처", "정확히 기억", "모르겠습니다", "확실하지",
        "선배해설", "필자", "복원자",
    ]
    kept = []
    for line in lines:
        plain = strip_html(line)
        if not plain:
            continue
        if any(word in plain for word in drop):
            continue
        kept.append(line.strip())
    return "<br>".join(kept)


def extract_apkg(src: Path, target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(src) as zf:
        zf.extractall(target)
    candidates = []
    for p in target.glob("collection.anki*"):
        if p.name.endswith(("-wal", "-shm")) or p.stat().st_size == 0:
            continue
        try:
            con = sqlite3.connect(p)
            tables = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
            con.close()
            if {"notes", "cards", "col"}.issubset(tables):
                candidates.append(p)
        except sqlite3.DatabaseError:
            pass
    if not candidates:
        raise RuntimeError(f"No valid Anki database in {src}")
    return max(candidates, key=lambda p: p.stat().st_size)


def repack(folder: Path, output: Path) -> None:
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not path.name.endswith(("-wal", "-shm")):
                zf.write(path, str(path.relative_to(folder)))


class AnkiDB:
    def __init__(self, db_path: Path):
        self.path = db_path
        self.con = sqlite3.connect(db_path)
        self.con.create_collation("unicase", unicase)
        self.cur = self.con.cursor()
        self.tables = {row[0] for row in self.cur.execute("select name from sqlite_master where type='table'")}
        self.modern = "notetypes" in self.tables and "decks" in self.tables
        self.now = int(time.time())
        self.model_names: dict[int, str] = {}
        self.model_fields: dict[int, list[str]] = {}
        self.deck_map: dict[int, str] = {}
        self.deck_json: dict[str, dict] | None = None
        self._load_models()
        self._load_decks()

    def _load_models(self):
        if self.modern:
            self.model_names = {int(mid): name for mid, name in self.cur.execute("select id,name from notetypes")}
            for mid in self.model_names:
                self.model_fields[mid] = [row[0] for row in self.cur.execute("select name from fields where ntid=? order by ord", (mid,))]
        else:
            raw = self.cur.execute("select models from col").fetchone()[0]
            models = json.loads(raw)
            for key, model in models.items():
                mid = int(key)
                self.model_names[mid] = model.get("name", str(mid))
                self.model_fields[mid] = [field.get("name", f"Field {idx+1}") for idx, field in enumerate(model.get("flds", []))]

    def _load_decks(self):
        if self.modern:
            self.deck_map = {int(did): name for did, name in self.cur.execute("select id,name from decks")}
        else:
            raw = self.cur.execute("select decks from col").fetchone()[0]
            self.deck_json = json.loads(raw)
            self.deck_map = {int(key): deck.get("name", str(key)) for key, deck in self.deck_json.items()}

    def find_model(self, marker: str) -> int:
        marker = marker.casefold()
        found = [(mid, name) for mid, name in self.model_names.items() if marker in name.casefold()]
        if not found:
            raise RuntimeError(f"No note type containing {marker}: {self.model_names}")
        return found[0][0]

    def find_jokbo_model(self) -> int:
        found = [(mid, name) for mid, name in self.model_names.items() if "족보" in name]
        if not found:
            raise RuntimeError(f"No 족보 note type: {self.model_names}")
        return found[0][0]

    def find_parent_deck(self, marker: str) -> tuple[int, str]:
        found = [(did, name) for did, name in self.deck_map.items() if marker in name]
        if not found:
            raise RuntimeError(f"No deck containing {marker}: {self.deck_map}")
        return min(found, key=lambda item: len(item[1]))

    def separator(self, parent_name: str) -> str:
        return SEP if SEP in parent_name else "::"

    def ensure_deck(self, name: str, template_did: int) -> int:
        for did, existing in self.deck_map.items():
            if existing == name:
                return did
        did = max(self.deck_map) + 1
        while did in self.deck_map:
            did += 1
        if self.modern:
            common, kind = self.cur.execute("select common,kind from decks where id=?", (template_did,)).fetchone()
            self.cur.execute(
                "insert into decks(id,name,mtime_secs,usn,common,kind) values(?,?,?,?,?,?)",
                (did, name, self.now, -1, common, kind),
            )
        else:
            assert self.deck_json is not None
            template = copy.deepcopy(self.deck_json[str(template_did)])
            template["id"] = did
            template["name"] = name
            template["mod"] = self.now
            template["usn"] = -1
            self.deck_json[str(did)] = template
        self.deck_map[did] = name
        return did

    def flush(self):
        if not self.modern:
            assert self.deck_json is not None
            self.cur.execute("update col set decks=?", (json.dumps(self.deck_json, ensure_ascii=False, separators=(",", ":")),))
        now_ms = int(time.time() * 1000)
        self.cur.execute("update col set mod=?,scm=?", (now_ms, now_ms))
        self.con.commit()

    def close(self):
        self.flush()
        self.con.close()


def fields_for(model_fields: list[str], primary: str, extra: str = "", third: str = "") -> list[str]:
    values = []
    for idx, name in enumerate(model_fields):
        low = name.casefold()
        if idx == 0 or low in {"text", "front", "문제번호"}:
            values.append(primary)
        elif "extra" in low or low in {"back", "정답 및 해설", "정답", "해설"}:
            values.append(extra)
        else:
            values.append(third)
    return values


def set_note(db: AnkiDB, nid: int, values: list[str], tags: str) -> None:
    primary = values[0] if values else ""
    db.cur.execute(
        "update notes set flds=?,sfld=?,csum=?,tags=?,mod=?,usn=-1 where id=?",
        (SEP.join(values), primary, checksum(primary), f" {tags.strip()} ", db.now, nid),
    )


def insert_cloze(db: AnkiDB, state: dict, mid: int, did: int, due: int, title: str, text: str, extra: str, tag_root: str) -> tuple[int, int]:
    nid = state["next"]
    cid = nid + 1
    state["next"] += 2
    primary = f"<b>{title}</b><br><br>{text}"
    values = fields_for(db.model_fields[mid], primary, extra)
    guid = "z" + hashlib.sha1(f"{nid}:{title}".encode("utf-8")).hexdigest()[:11]
    db.cur.execute(
        "insert into notes(id,guid,mid,mod,usn,tags,flds,sfld,csum,flags,data) values(?,?,?,?,?,?,?,?,?,?,?)",
        (nid, guid, mid, db.now, -1, f" {tag_root} concept cloze concept_first ", SEP.join(values), primary, checksum(primary), 0, ""),
    )
    db.cur.execute(
        "insert into cards(id,nid,did,ord,mod,usn,type,queue,due,ivl,factor,reps,lapses,left,odue,odid,flags,data) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, nid, did, 0, db.now, -1, 0, 0, due, 0, 0, 0, 0, 0, 0, 0, 0, ""),
    )
    return nid, cid


def topic_link(question: str, kind: str) -> str:
    q = strip_html(question).casefold()
    if kind == "gyne":
        mapping = [
            (["adenomy", "샘근육"], "자궁샘근육증"),
            (["myoma", "근종"], "자궁근종"),
            (["endometrial carcinoma", "자궁내막암"], "자궁내막암"),
            (["teratoma", "기형종"], "난소기형종"),
            (["endometriosis", "자궁내막증"], "자궁내막증과 지방억제 영상"),
            (["ectopic", "tubal pregnancy", "자궁외", "난관임신"], "난관임신"),
            (["trophoblastic", "gtt", "영양막"], "임신영양막질환"),
            (["hsg", "자궁난관", "hydrosalpinx", "tubal occlusion", "synechia"], "HSG 참고 범위"),
        ]
    else:
        mapping = [
            (["ovarian reserve", "난소 예비", "amh", "afc"], "난소예비능 평가법"),
            (["hydrosalpinx", "난관수종"], "난관수종"),
            (["semen", "정액", "sperm"], "정액검사"),
            (["hsg", "자궁난관"], "자궁난관조영술"),
            (["basal body", "기초체온", "progesterone", "배란"], "배란 확인"),
            (["asherman", "유착", "synechia"], "자궁강 유착"),
            (["endometriosis", "자궁내막증"], "자궁내막증과 난임"),
            (["cervical mucus", "점액", "pct"], "자궁경부 점액과 구족보"),
        ]
    for tokens, label in mapping:
        if any(token in q for token in tokens):
            return label
    return "관련 JBL 개념"


def rewrite_jokbo(db: AnkiDB, nid: int, mid: int, kind: str, status_note: str = "") -> None:
    row = db.cur.execute("select flds,tags from notes where id=?", (nid,)).fetchone()
    values = row[0].split(SEP)
    tags = row[1] or ""
    names = db.model_fields[mid]
    while len(values) < len(names):
        values.append("")
    q_idx = next((i for i, name in enumerate(names) if "본문" in name or "question" in name.casefold()), min(1, len(values)-1))
    a_idx = next((i for i, name in enumerate(names) if "정답" in name or "해설" in name or "answer" in name.casefold()), len(values)-1)
    question = values[q_idx]
    old = clean_explanation(values[a_idx])
    pieces = [p.strip() for p in re.split(r"(?i)<br\s*/?>", old) if strip_html(p)]
    answer = ""
    body = []
    for piece in pieces:
        plain = strip_html(piece)
        if not answer and (re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩0-9]", plain) or len(plain) <= 70):
            answer = plain
        else:
            body.append(piece)
    if not answer:
        answer = "기존 족보 정답"
    if not body:
        body = ["제시된 영상 또는 임상 단서를 JBL의 핵심 기준과 연결해 판단한다."]
    body_text = "<br>".join(body)
    status_html = f"<br><br><b>범위 메모</b><br>{status_note}" if status_note else ""
    values[a_idx] = clean_symbols(
        f"<b>정답</b><br>{html.escape(answer)}<br><br>"
        f"<b>판단 근거</b><br>{body_text}<br><br>"
        f"<b>연결 JBL</b><br>{topic_link(question, kind)}{status_html}"
    )
    values = [clean_symbols(v) for v in values]
    set_note(db, nid, values, tags.strip() + " explanation_revised")


def parse_year(code: str) -> int:
    m = re.search(r"\((\d{2})[- ]", code)
    return int(m.group(1)) if m else 0


def build_one(src: Path, out: Path, kind: str, concepts: list[dict]) -> dict:
    work = OUTPUT / f"{kind}_work"
    db_path = extract_apkg(src, work)
    db = AnkiDB(db_path)
    cloze_mid = db.find_model("cloze")
    basic_mid = db.find_model("basic")
    jokbo_mid = db.find_jokbo_model()
    original_mids = {nid: mid for nid, mid in db.cur.execute("select id,mid from notes").fetchall()}
    before_notes = db.cur.execute("select count(*) from notes").fetchone()[0]
    before_cards = db.cur.execute("select count(*) from cards").fetchone()[0]
    before_jokbo = db.cur.execute("select count(*) from notes where mid=?", (jokbo_mid,)).fetchone()[0]

    jbl_parent_did, jbl_parent_name = db.find_parent_deck("2. JBL")
    jokbo_parent_did, jokbo_parent_name = db.find_parent_deck("3. 족보")
    sep = db.separator(jbl_parent_name)

    existing_jbl_dids = {did for did, name in db.deck_map.items() if name == jbl_parent_name or name.startswith(jbl_parent_name + sep)}
    existing_jokbo_dids = {did for did, name in db.deck_map.items() if name == jokbo_parent_name or name.startswith(jokbo_parent_name + sep)}

    topic_dids = {}
    for concept in concepts:
        label = concept["deck"]
        if label not in topic_dids:
            topic_dids[label] = db.ensure_deck(jbl_parent_name + sep + label, jbl_parent_did)
    application_did = db.ensure_deck(jbl_parent_name + sep + ("9. 영상 적용" if kind == "gyne" else "10. 사례와 영상 적용"), jbl_parent_did)
    optional_did = db.ensure_deck(jbl_parent_name + sep + ("10. 보충 카드" if kind == "gyne" else "11. 보충 카드"), jbl_parent_did)
    recent_jokbo_did = db.ensure_deck(jokbo_parent_name + sep + "1. 최근 및 반복 족보", jokbo_parent_did)
    old_jokbo_did = db.ensure_deck(jokbo_parent_name + sep + "2. 구족보", jokbo_parent_did)
    outscope_jokbo_did = db.ensure_deck(jokbo_parent_name + sep + "3. 타강의 또는 미수업 참고", jokbo_parent_did)

    if existing_jbl_dids:
        marks = ",".join("?" for _ in existing_jbl_dids)
        db.cur.execute(f"update cards set did=?,queue=-1,mod=?,usn=-1 where did in ({marks})", [optional_did, db.now, *sorted(existing_jbl_dids)])

    cards_by_nid = defaultdict(list)
    for row in db.cur.execute("select id,nid,did,ord from cards").fetchall():
        cards_by_nid[row[1]].append(row)

    candidates = []
    for nid, mid, flds, tags in db.cur.execute("select id,mid,flds,tags from notes").fetchall():
        if mid != basic_mid:
            continue
        cards = cards_by_nid.get(nid, [])
        if not cards or not any(card[2] in existing_jbl_dids for card in cards):
            continue
        values = flds.split(SEP)
        front = values[0] if values else ""
        low = (tags or "").casefold() + " " + strip_html(front).casefold()
        if "atlas" in low or "참고용 이미지" in low:
            continue
        candidates.append({"nid": nid, "title": strip_html(front).casefold(), "values": values, "cards": cards})

    next_id = max(db.cur.execute("select max(id) from notes").fetchone()[0] or 0, db.cur.execute("select max(id) from cards").fetchone()[0] or 0) + 1000
    state = {"next": next_id}
    due = 1
    used = set()
    new_concept_nids = []
    active_application_cards = []
    tag_root = "gynecologic_imaging" if kind == "gyne" else "infertility"

    for concept in concepts:
        did = topic_dids[concept["deck"]]
        nid, cid = insert_cloze(db, state, cloze_mid, did, due, concept["title"], concept["text"], concept["extra"], tag_root)
        new_concept_nids.append(nid)
        due += 1
        for pattern in concept.get("apps", []):
            p = pattern.casefold()
            matched = next((item for item in candidates if item["nid"] not in used and p in item["title"]), None)
            if not matched:
                continue
            used.add(matched["nid"])
            set_note(db, matched["nid"], [clean_symbols(v) for v in matched["values"]], tag_root + " application")
            for cid0, _, _, _ in matched["cards"]:
                db.cur.execute(
                    "update cards set did=?,type=0,queue=0,due=?,ivl=0,factor=0,reps=0,lapses=0,left=0,odue=0,odid=0,mod=?,usn=-1 where id=?",
                    (did, due, db.now, cid0),
                )
                active_application_cards.append(cid0)
                due += 1

    for item in candidates:
        if item["nid"] in used:
            continue
        joined = " ".join(item["values"]).casefold()
        if "<img" not in joined:
            continue
        used.add(item["nid"])
        set_note(db, item["nid"], [clean_symbols(v) for v in item["values"]], tag_root + " application image_review")
        for cid0, _, _, _ in item["cards"]:
            db.cur.execute(
                "update cards set did=?,type=0,queue=0,due=?,ivl=0,factor=0,reps=0,lapses=0,left=0,odue=0,odid=0,mod=?,usn=-1 where id=?",
                (application_did, due, db.now, cid0),
            )
            active_application_cards.append(cid0)
            due += 1

    jokbo_notes = []
    for nid, mid, flds in db.cur.execute("select id,mid,flds from notes where mid=?", (jokbo_mid,)).fetchall():
        cards = cards_by_nid.get(nid, [])
        if not cards or not any(card[2] in existing_jokbo_dids for card in cards):
            continue
        values = flds.split(SEP)
        code = strip_html(values[0] if values else "")
        full = strip_html(" ".join(values)).casefold()
        year = parse_year(code)
        if kind == "gyne":
            out_scope = any(token in full for token in ["hsg", "자궁난관조영", "hydrosalpinx", "tubal occlusion", "uterine synechia", "bicornuate"])
        else:
            out_scope = any(token in full for token in ["ohss", "gnrh antagonist", "icsi", "intracytoplasmic", "gift", "zift", "assisted reproductive techniques"])
        if out_scope:
            target, queue, status = outscope_jokbo_did, -1, "현재 강의에서 직접 다루지 않았거나 별도 ART 강의 범위인 문제이다. 문제는 보존하되 기본 복습에서는 제외했다."
        elif year and year < 18:
            target, queue, status = old_jokbo_did, 0, "구교수 또는 오래된 출제 사례이다. 현재 강의와 겹치는 개념을 중심으로 학습한다."
        else:
            target, queue, status = recent_jokbo_did, 0, ""
        rewrite_jokbo(db, nid, jokbo_mid, kind, status)
        for cid0, _, _, _ in cards:
            db.cur.execute(
                "update cards set did=?,type=0,queue=?,due=0,ivl=0,factor=0,reps=0,lapses=0,left=0,odue=0,odid=0,mod=?,usn=-1 where id=?",
                (target, queue, db.now, cid0),
            )
        jokbo_notes.append((nid, target, queue, year, code))

    for target in [recent_jokbo_did, old_jokbo_did]:
        seq = 1
        rows = [row for row in jokbo_notes if row[1] == target and row[2] >= 0]
        for nid, _, _, year, code in sorted(rows, key=lambda row: (row[3], row[4]), reverse=True):
            for cid0, in db.cur.execute("select id from cards where nid=? order by ord", (nid,)).fetchall():
                db.cur.execute("update cards set due=? where id=?", (seq, cid0))
                seq += 1

    db.flush()
    integrity = db.cur.execute("pragma integrity_check").fetchone()[0]
    changed_types = [nid for nid, mid in original_mids.items() if db.cur.execute("select mid from notes where id=?", (nid,)).fetchone()[0] != mid]
    active_jbl_rows = db.cur.execute("select c.due,n.flds from cards c join notes n on c.nid=n.id where c.did in (%s) and c.queue>=0 order by c.due" % ",".join("?" for _ in set(topic_dids.values()) | {application_did}), tuple(set(topic_dids.values()) | {application_did})).fetchall()
    due_values = [row[0] for row in active_jbl_rows]
    due_ok = due_values == list(range(1, len(due_values) + 1))
    active_text = "\n".join(row[1] for row in active_jbl_rows)
    bad_symbols = {symbol: active_text.count(symbol) for symbol in ["•", "·", "→", "⇒"] if symbol in active_text}
    question_style = []
    for nid in new_concept_nids:
        flds = db.cur.execute("select flds from notes where id=?", (nid,)).fetchone()[0]
        first = flds.split(SEP)[0]
        if any(term in strip_html(first) for term in ["무엇입니까", "답해 보세요", "진단은?"]):
            question_style.append(nid)
        if "{{c1::" not in first:
            question_style.append(nid)
    after_notes = db.cur.execute("select count(*) from notes").fetchone()[0]
    after_cards = db.cur.execute("select count(*) from cards").fetchone()[0]
    after_jokbo = db.cur.execute("select count(*) from notes where mid=?", (jokbo_mid,)).fetchone()[0]

    media_path = work / "media"
    media_names = set(json.load(open(media_path, encoding="utf-8")).values()) if media_path.exists() else set()
    refs = set()
    for flds, in db.cur.execute("select flds from notes").fetchall():
        refs.update(re.findall(r'<img[^>]+src=["\']([^"\']+)', flds))
    missing_media = sorted(name for name in refs if name not in media_names)

    db.close()
    for extra in work.glob("collection.anki*-wal"):
        extra.unlink(missing_ok=True)
    for extra in work.glob("collection.anki*-shm"):
        extra.unlink(missing_ok=True)
    repack(work, out)
    with zipfile.ZipFile(out) as zf:
        bad_zip = zf.testzip()

    return {
        "schema": "modern" if db.modern else "legacy",
        "before_notes": before_notes,
        "before_cards": before_cards,
        "after_notes": after_notes,
        "after_cards": after_cards,
        "new_concepts": len(new_concept_nids),
        "active_application_cards": len(active_application_cards),
        "active_jbl_cards": len(active_jbl_rows),
        "jokbo_notes_preserved": before_jokbo == after_jokbo,
        "recent_jokbo": sum(1 for row in jokbo_notes if row[1] == recent_jokbo_did),
        "old_jokbo": sum(1 for row in jokbo_notes if row[1] == old_jokbo_did),
        "out_of_scope_jokbo": sum(1 for row in jokbo_notes if row[1] == outscope_jokbo_did),
        "integrity": integrity,
        "existing_note_types_changed": len(changed_types),
        "due_sequence_ok": due_ok,
        "question_style_concept_cards": question_style,
        "bad_symbols": bad_symbols,
        "missing_media": missing_media,
        "zip_test": bad_zip,
        "size_bytes": out.stat().st_size,
    }


def main():
    assert STYLE_MD.exists() and STYLE_MD.stat().st_size > 1000
    gyne = build_one(GYNE_SRC, GYNE_OUT, "gyne", source.GYNE_CONCEPTS)
    infertility = build_one(INF_SRC, INF_OUT, "infertility", source.INF_CONCEPTS)
    report = ["두 덱 개념 선행형 최종 검증", ""]
    for name, result in [("산부인과 영상진단", gyne), ("난임", infertility)]:
        report.append(f"[{name}]")
        for key, value in result.items():
            report.append(f"{key}: {value}")
        report.append("")
    REPORT_OUT.write_text("\n".join(report), encoding="utf-8")
    print(REPORT_OUT.read_text(encoding="utf-8"))
    failures = []
    for name, result in [("gyne", gyne), ("infertility", infertility)]:
        if result["integrity"] != "ok": failures.append(name + " integrity")
        if result["existing_note_types_changed"] != 0: failures.append(name + " note types")
        if not result["due_sequence_ok"]: failures.append(name + " due")
        if result["question_style_concept_cards"]: failures.append(name + " question-first")
        if result["bad_symbols"]: failures.append(name + " symbols")
        if result["missing_media"]: failures.append(name + " media")
        if result["zip_test"] is not None: failures.append(name + " zip")
        if not result["jokbo_notes_preserved"]: failures.append(name + " jokbo")
    if failures:
        raise SystemExit("Validation failed: " + ", ".join(failures))


if __name__ == "__main__":
    main()
