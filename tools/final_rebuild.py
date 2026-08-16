#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

SEP = "\x1f"
ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "work_inputs"
OUTPUT = ROOT / "outputs"
OUTPUT.mkdir(exist_ok=True)

GYNE_SRC = INPUT / "gyne_source.apkg"
INF_SRC = INPUT / "infertility_source.apkg"
LEE_WONJAE = INPUT / "reference_lee_wonjae.apkg"
LEE_SANGHOON = INPUT / "reference_lee_sanghoon.apkg"
STYLE_MD = INPUT / "concept_style_reference.md"

GYNE_OUT = OUTPUT / "산부인과_영상진단_최종본_개념선행_족보통합.apkg"
INF_OUT = OUTPUT / "난임_Infertility_최종본_개념선행_족보통합.apkg"
REPORT = OUTPUT / "두_덱_개념선행_최종검증.txt"


def collation(a, b):
    a = (a or "").casefold()
    b = (b or "").casefold()
    return (a > b) - (a < b)


def strip_html(value):
    value = re.sub(r"(?i)<br\s*/?>", " ", value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def csum(value):
    digest = hashlib.sha1(strip_html(value).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def clean_symbols(value):
    if not value:
        return value
    replacements = {
        "•": "<br>",
        "·": "과",
        "→": ": ",
        "⇒": ": ",
        "⇢": ": ",
        ">>": "보다 우수",
        "↔": "와 ",
        "✓": "",
        "✔": "",
        "▶": "",
        "▷": "",
        "※": "",
        "♘": "",
        "～": "에서",
        "~": "에서",
        "&nbsp;": " ",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"[🫶ㅠㅜ😂🤣]+", "", value)
    value = re.sub(r"(?i)<br>\s*<br>\s*<br>+", "<br><br>", value)
    value = re.sub(r"\s+([,.:;])", r"\1", value)
    return value.strip()


def remove_chatty(value):
    value = clean_symbols(value or "")
    lines = re.split(r"(?i)<br\s*/?>|\n", value)
    kept = []
    drop_words = [
        "죄송", "힘내", "화이팅", "ㅋㅋ", "ㅠㅠ", "학편위", "지나가는 사람",
        "정확한 복원", "복원을 못", "복원이", "개인적으로", "다들", "왕족입니다",
        "족보를 맹신", "내용출처", "출처:", "메뉴얼 그대로", "토스를 켜",
        "종강", "필자는", "복원자", "모르겠습니다", "헷갈렸", "확실하지",
    ]
    for line in lines:
        t = strip_html(line)
        if not t:
            continue
        if any(word in t for word in drop_words):
            continue
        kept.append(line.strip())
    return "<br>".join(kept)


def normalize_title(text):
    return strip_html(text).casefold()


def extract_apkg(src, target):
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(src) as zf:
        zf.extractall(target)
    db = target / "collection.anki2"
    if not db.exists():
        candidates = list(target.glob("collection.anki*"))
        candidates = [p for p in candidates if p.stat().st_size > 0]
        if not candidates:
            raise RuntimeError(f"No Anki database in {src}")
        db = max(candidates, key=lambda p: p.stat().st_size)
    return db


def repack(folder, out):
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not path.name.endswith(("-wal", "-shm")):
                zf.write(path, str(path.relative_to(folder)))


def model_info(cur):
    names = {row[0]: row[1] for row in cur.execute("select id,name from notetypes")}
    cloze = next((mid for mid, name in names.items() if "cloze" in name.casefold()), None)
    basic = next((mid for mid, name in names.items() if "basic" in name.casefold()), None)
    jokbo = next((mid for mid, name in names.items() if "족보" in name), None)
    if not all((cloze, basic, jokbo)):
        raise RuntimeError(f"Could not identify note types: {names}")
    fields = {}
    for mid in names:
        fields[mid] = [row[0] for row in cur.execute("select name from fields where ntid=? order by ord", (mid,))]
    return names, fields, cloze, basic, jokbo


def deck_names(cur):
    return {row[0]: row[1] for row in cur.execute("select id,name from decks")}


def find_parent(decks, marker):
    matches = [(did, name) for did, name in decks.items() if marker in name]
    if not matches:
        raise RuntimeError(f"No deck containing {marker}")
    return min(matches, key=lambda item: len(item[1]))


def ensure_deck(cur, name, template_did, now, reserved):
    row = cur.execute("select id from decks where name=?", (name,)).fetchone()
    if row:
        return row[0]
    common, kind = cur.execute("select common,kind from decks where id=?", (template_did,)).fetchone()
    did = max(reserved) + 1
    while cur.execute("select 1 from decks where id=?", (did,)).fetchone():
        did += 1
    reserved.add(did)
    cur.execute(
        "insert into decks(id,name,mtime_secs,usn,common,kind) values(?,?,?,?,?,?)",
        (did, name, now, -1, common, kind),
    )
    return did


def build_fields(field_names, primary, extra="", third=""):
    values = []
    for idx, name in enumerate(field_names):
        low = name.casefold()
        if idx == 0 or low in {"text", "front", "문제번호"}:
            values.append(primary)
        elif "extra" in low or low in {"back", "정답 및 해설", "정답", "해설"}:
            values.append(extra)
        else:
            values.append(third)
    return values


def html_join(title, body):
    return f"<b>{title}</b><br><br>{body}"


def insert_cloze(cur, state, mid, field_names, did, due, title, text, extra, tags, now):
    nid = state["next_id"]
    state["next_id"] += 2
    cid = nid + 1
    primary = html_join(title, text)
    values = build_fields(field_names, primary, extra)
    flds = SEP.join(values)
    guid = "f" + hashlib.sha1(f"{nid}-{title}".encode()).hexdigest()[:11]
    cur.execute(
        "insert into notes(id,guid,mid,mod,usn,tags,flds,sfld,csum,flags,data) values(?,?,?,?,?,?,?,?,?,?,?)",
        (nid, guid, mid, now, -1, f" {tags.strip()} ", flds, primary, csum(primary), 0, ""),
    )
    cur.execute(
        "insert into cards(id,nid,did,ord,mod,usn,type,queue,due,ivl,factor,reps,lapses,left,odue,odid,flags,data) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, nid, did, 0, now, -1, 0, 0, due, 0, 0, 0, 0, 0, 0, 0, 0, ""),
    )
    return cid, nid


def get_note_fields(cur, nid):
    row = cur.execute("select mid,flds,tags from notes where id=?", (nid,)).fetchone()
    if not row:
        return None
    return row[0], row[1].split(SEP), row[2]


def set_note_fields(cur, nid, values, tags, now):
    primary = values[0] if values else ""
    cur.execute(
        "update notes set flds=?,sfld=?,csum=?,tags=?,mod=?,usn=-1 where id=?",
        (SEP.join(values), primary, csum(primary), f" {tags.strip()} ", now, nid),
    )


def classify_topic(text, topic_map, default):
    low = normalize_title(text)
    for key, did in topic_map:
        if any(token.casefold() in low for token in key):
            return did
    return default


def activate_matching_app(cur, candidates, used, patterns, did, due, now):
    activated = []
    for pattern in patterns:
        p = pattern.casefold()
        for item in candidates:
            if item["nid"] in used:
                continue
            if p in item["title"]:
                used.add(item["nid"])
                values = item["fields"]
                values = [clean_symbols(v) for v in values]
                set_note_fields(cur, item["nid"], values, "gynecologic-imaging application" if item["kind"] == "gyne" else "infertility application", now)
                for cid in item["cards"]:
                    cur.execute(
                        "update cards set did=?,type=0,queue=0,due=?,ivl=0,factor=0,reps=0,lapses=0,left=0,odue=0,odid=0,mod=?,usn=-1 where id=?",
                        (did, due, now, cid),
                    )
                    due += 1
                    activated.append(cid)
                break
    return due, activated


def topic_link(question, kind):
    q = strip_html(question).casefold()
    if kind == "gyne":
        mapping = [
            (["adenomy", "샘근육"], "자궁샘근육증의 접합부 비후와 내부 고신호 병소"),
            (["myoma", "근종"], "자궁근종의 경계가 좋은 T2 저신호 종괴"),
            (["endometrial carcinoma", "자궁내막암"], "불규칙한 자궁내막 종괴와 근층 침범"),
            (["teratoma", "기형종"], "지방 확인과 지방억제 영상"),
            (["endometriosis", "자궁내막증"], "반복 출혈과 지방억제 후 남는 T1 고신호"),
            (["tubal pregnancy", "ectopic", "자궁외", "난관임신"], "부속기 임신낭과 혈복강"),
            (["gtt", "trophoblastic", "영양막"], "임신영양막질환과 난포막황체낭"),
            (["hsg", "자궁난관", "synechia", "hydrosalpinx", "tubal occlusion"], "HSG 참고 범위"),
        ]
    else:
        mapping = [
            (["ovarian reserve", "난소 예비", "amh", "afc"], "난소예비능 평가법"),
            (["hydrosalpinx", "난관수종"], "난관수종과 체외수정 전 난관절제술"),
            (["semen", "정액", "sperm"], "정액검사 해석과 반복검사"),
            (["hsg", "자궁난관"], "자궁난관조영술의 시기와 영상 해석"),
            (["basal body", "기초체온", "progesterone", "배란"], "배란 확인 방법"),
            (["asherman", "유착", "synechia"], "자궁강 유착의 진단과 치료"),
            (["endometriosis", "자궁내막증"], "자궁내막증이 난임을 일으키는 기전"),
            (["cervical mucus", "점액", "pct"], "자궁경부 점액과 구교수 족보"),
        ]
    for tokens, label in mapping:
        if any(token in q for token in tokens):
            return label
    return "해당 JBL 개념 카드"


def rewrite_jokbo(cur, nid, field_names, kind, now):
    mid, values, tags = get_note_fields(cur, nid)
    if not values:
        return
    while len(values) < 3:
        values.append("")
    question = values[1] if len(values) > 1 else values[0]
    old = values[2] if len(values) > 2 else values[-1]
    cleaned = remove_chatty(old)
    parts = [p.strip() for p in re.split(r"(?i)<br\s*/?>", cleaned) if strip_html(p)]
    answer = ""
    body_parts = []
    for part in parts:
        plain = strip_html(part)
        if not answer and (re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩0-9]", plain) or len(plain) < 80):
            answer = plain
            continue
        body_parts.append(part)
    if not answer:
        answer = "기존 족보 정답을 확인하세요."
    if not body_parts:
        body_parts = ["문제의 영상 또는 임상 단서와 연결되는 핵심 개념을 확인합니다."]
    body = "<br>".join(body_parts)
    body = clean_symbols(body)
    extra = (
        f"<b>정답</b><br>{html.escape(answer)}<br><br>"
        f"<b>핵심 해설</b><br>{body}<br><br>"
        f"<b>연결 JBL</b><br>{topic_link(question, kind)}"
    )
    values[2] = extra
    values = [clean_symbols(v) for v in values]
    set_note_fields(cur, nid, values, tags.strip() + " explanation_revised", now)


def expected_check(cur, patterns):
    all_text = "\n".join(row[0] for row in cur.execute("select flds from notes"))
    return {pat: (pat in all_text) for pat in patterns}


def inspect_reference(apkg):
    work = OUTPUT / (apkg.stem + "_inspect")
    db = extract_apkg(apkg, work)
    con = sqlite3.connect(db)
    con.create_collation("unicase", collation)
    cur = con.cursor()
    notes = cur.execute("select count(*) from notes").fetchone()[0]
    cards = cur.execute("select count(*) from cards").fetchone()[0]
    samples = []
    for flds in cur.execute("select flds from notes limit 5"):
        samples.append(strip_html(flds[0].split(SEP)[0])[:120])
    con.close()
    shutil.rmtree(work, ignore_errors=True)
    return notes, cards, samples


GYNE_CONCEPTS = [
    {
        "deck": "1. 검사법과 정상 구조",
        "title": "부인과 초음파 검사법",
        "text": "복벽경유초음파는 자궁 뒤쪽을 보기 위한 음향창을 만들기 위해 방광을 {{c1::채운 상태}}에서 시행한다.<br>질경유초음파는 방광을 {{c1::비운 상태}}에서 시행하며 자궁과 난소에 더 가까이 접근하므로 해상도가 좋다.",
        "extra": "복벽경유에서는 찬 방광이 초음파가 지나가는 창 역할을 한다. 질경유에서는 탐촉자가 자궁 가까이 접근하므로 방광을 채울 필요가 없다.",
        "apps": [],
    },
    {
        "deck": "1. 검사법과 정상 구조",
        "title": "MRI 신호를 읽는 최소 원칙",
        "text": "난소 병변이 T1 강조영상에서 밝게 보이면 지방이나 혈액을 생각한다.<br>지방억제 영상에서 신호가 {{c1::감소하면 지방}}, 고신호가 {{c1::유지되면 혈액}}을 우선 생각한다.",
        "extra": "이 원칙은 난소기형종과 자궁내막증을 구분하는 데 직접 사용된다. 처음에는 병명을 맞히기보다 지방억제 전후 신호 변화를 먼저 본다.",
        "apps": ["지방과 혈액", "t1 고신호"],
    },
    {
        "deck": "1. 검사법과 정상 구조",
        "title": "정상 자궁 MRI T2 구조",
        "text": "정상 자궁체부는 T2 강조영상에서 세 층으로 보인다.<br>안쪽 자궁내막은 {{c1::고신호}}, 중간 접합부는 {{c1::저신호}}, 바깥 자궁근층은 {{c1::중간신호}}를 보인다.",
        "extra": "접합부가 정상적으로 어둡다는 것을 알아야 자궁샘근육증의 접합부 비후와 자궁내막암의 근층 침범을 이해할 수 있다.",
        "apps": ["정상 자궁체부 t2"],
    },
    {
        "deck": "2. 자궁근종과 자궁샘근육증",
        "title": "자궁근종",
        "text": "자궁근종은 자궁근층에서 발생하는 {{c1::경계가 좋은 독립 고형종괴}}이다.<br>MRI T2 강조영상에서는 대개 {{c1::저신호}}를 보이며, 변성이 생기면 내부가 {{c1::비균질}}하게 보일 수 있다.",
        "extra": "영상에서는 먼저 경계가 선명한 둥근 종괴가 있는지 본다. 변성된 근종은 자궁육종과 감별이 어려울 수 있지만 전형적인 근종은 경계가 비교적 뚜렷하다.",
        "apps": [],
    },
    {
        "deck": "2. 자궁근종과 자궁샘근육증",
        "title": "자궁샘근육증",
        "text": "자궁샘근육증은 {{c1::자궁내막조직이 자궁근층 안에 존재}}하는 질환이다.<br>MRI에서는 접합부가 {{c1::경계 불분명하게 두꺼워지고}}, 저신호 부위 안에 {{c1::작은 고신호 병소}}가 섞여 보인다.",
        "extra": "작은 고신호 병소는 근층 안의 자궁내막샘이나 출혈성 병소를 반영한다. 독립된 둥근 종괴보다 자궁근층 자체가 넓게 두꺼워지는 형태가 중요하다.",
        "apps": [],
    },
    {
        "deck": "2. 자궁근종과 자궁샘근육증",
        "title": "자궁근종과 자궁샘근육증의 감별",
        "text": "두 질환은 모두 T2 저신호를 보일 수 있다.<br>자궁근종은 {{c1::경계가 좋은 독립 종괴}}, 자궁샘근육증은 {{c1::경계가 흐린 접합부 비후와 내부의 작은 고신호 병소}}가 핵심이다.",
        "extra": "영상에서 어둡다는 사실만으로 구분하지 않는다. 경계가 깨끗한지, 작은 밝은 점이 섞여 있는지를 순서대로 본다.",
        "apps": ["자궁근층의 독립 종괴", "t2 저신호 자궁 병변", "근종 vs 샘근육증"],
    },
    {
        "deck": "3. 자궁내막과 자궁경부",
        "title": "양성 자궁내막 종괴",
        "text": "자궁강의 양성 종괴는 기본적으로 {{c1::경계가 좋은 자궁내막 종괴}}로 보인다.<br>점막밑근종은 T2 {{c1::저신호}}, 자궁내막용종은 T2 {{c1::중간신호}}를 보인다.",
        "extra": "두 병변은 모두 경계가 매끈할 수 있으므로 신호를 함께 본다. 경계가 불규칙해지면 자궁내막암을 생각한다.",
        "apps": [],
    },
    {
        "deck": "3. 자궁내막과 자궁경부",
        "title": "자궁내막암",
        "text": "자궁내막암의 대표 영상소견은 크기나 개수보다 {{c1::불규칙한 자궁내막 종괴}}라는 점이 중요하다.<br>가장 중요한 예후 인자는 {{c1::자궁근층 침범 깊이}}이며 이를 평가할 때 MRI가 CT보다 유용하다.",
        "extra": "양성 내막종괴는 경계가 좋은 반면 자궁내막암은 내막을 따라 지저분하고 불규칙하게 보인다.",
        "apps": ["4-way 감별", "자궁내막/자궁 종괴"],
    },
    {
        "deck": "3. 자궁내막과 자궁경부",
        "title": "자궁경부암에서 영상의 역할",
        "text": "자궁경부암은 Pap smear와 조직검사로 {{c1::임상적 및 병리학적으로 진단}}한다.<br>CT와 MRI의 주된 역할은 {{c1::병기 평가}}이며 국소 병기 평가에는 {{c1::MRI가 CT보다 유용}}하다.",
        "extra": "영상 문제에서는 자궁경부암인지 확진하는 것보다 어디까지 퍼졌는지를 보는 사고방식이 중요하다.",
        "apps": [],
    },
    {
        "deck": "3. 자궁내막과 자궁경부",
        "title": "자궁경부암 영상 병기",
        "text": "자궁주위조직 침범은 FIGO {{c1::IIB}}, 골반벽 침범이나 수신증은 {{c1::IIIB}}, 방광이나 직장 침범은 {{c1::IVA}}에 해당한다.",
        "extra": "자궁주위조직은 자궁경부 주변의 느슨한 결합조직이다. 이 부위에 종양성 가닥이나 비대칭 돌출이 보이면 침범을 생각한다.",
        "apps": ["parametrial invasion", "iib vs iva"],
    },
    {
        "deck": "3. 자궁내막과 자궁경부",
        "title": "자궁육종",
        "text": "자궁육종은 {{c1::크고 불규칙한 종괴}}, {{c1::경계 불분명}}, {{c1::비균질한 내부}}를 보이는 공격적인 형태가 특징이다.",
        "extra": "한 가지 특이 소견으로 진단하지 않는다. 전형적인 자궁근종은 경계가 좋고 T2 저신호지만 변성된 근종은 자궁육종과 비슷해질 수 있다.",
        "apps": [],
    },
    {
        "deck": "4. 임신영양막질환",
        "title": "임신영양막질환의 구조",
        "text": "임신영양막질환은 임신과 관련된 영양막의 비정상 증식이다.<br>포상기태는 {{c1::완전포상기태와 부분포상기태}}, 임신영양막종양은 {{c1::침윤성 포상기태와 융모암}}을 포함한다.<br>혈중 {{c1::hCG가 높고}} 난포막황체낭이 동반될 수 있다.",
        "extra": "먼저 포상기태와 종양의 분류를 잡는다. 종양은 자궁근층을 침범하는 불규칙한 종괴로 보일 수 있다.",
        "apps": ["gtt를 지지", "근층 침범"],
    },
    {
        "deck": "4. 임신영양막질환",
        "title": "완전포상기태",
        "text": "완전포상기태는 자궁강 안에 {{c1::수많은 낭성 융모}}가 모인 종괴를 형성한다.<br>초음파에서는 {{c1::눈보라 또는 포도송이 모양}}, CT에서는 낭성 공간 사이의 {{c1::강하게 조영되는 격막}}이 특징적이다.",
        "extra": "동글동글한 낭성 공간이 포도송이처럼 모여 있는 그림을 떠올리면 된다.",
        "apps": ["포상기태"],
    },
    {
        "deck": "5. 기능성 난소낭종",
        "title": "기능성 난소낭종",
        "text": "난포낭은 {{c1::얇은 벽을 가진 단방성 낭종}}, 황체낭은 {{c1::두꺼운 벽과 출혈 및 파열}}, 난포막황체낭은 {{c1::높은 hCG와 양측성 다방성 큰 낭종}}으로 정리한다.",
        "extra": "난포낭은 얇고 단순하다. 황체낭은 두껍고 출혈한다. 난포막황체낭은 높은 hCG와 연결한다.",
        "apps": [],
    },
    {
        "deck": "5. 기능성 난소낭종",
        "title": "출혈성 난소낭종과 파열",
        "text": "출혈성 난소낭종에서는 {{c1::액체 액체 층 또는 고음영 낭종}}이 보일 수 있다.<br>파열을 직접 지지하는 소견은 {{c1::낭종벽 결손과 혈복강}}이다.",
        "extra": "피가 낭종 안에만 있으면 출혈성 낭종이다. 피가 복강으로 나오고 벽이 끊겨 있으면 파열이다.",
        "apps": ["출혈성 난소낭종", "파열 여부", "결정 소견"],
    },
    {
        "deck": "6. 난소종양",
        "title": "난소종괴의 첫 접근",
        "text": "난소종괴를 보면 먼저 고형인지 낭성인지 나눈다.<br>{{c1::고형 종괴는 우선 종양}}으로 접근하고, 낭성 종괴에는 {{c1::기능성 낭종, 낭성 종양, 난관난소농양, 자궁내막증}}이 모두 포함될 수 있다.",
        "extra": "고형이면 먼저 종양을 생각한다. 낭성이면 종양이라고 단정하지 않고 기능성 병변과 염증, 출혈성 병변을 함께 본다.",
        "apps": [],
    },
    {
        "deck": "6. 난소종양",
        "title": "난소 고형종양",
        "text": "난소의 고형 종괴는 종양으로 접근한다.<br>양성 섬유종과 난포막종은 T2 강조영상에서 특징적으로 {{c1::저신호}}를 보이며, 악성 고형종양의 신호는 {{c1::다양}}하다.",
        "extra": "난소 고형종괴가 T2 저신호이면 섬유종이나 난포막종을 먼저 떠올린다. 이 내용은 보충 감별로 사용한다.",
        "apps": [],
    },
    {
        "deck": "6. 난소종양",
        "title": "난소 낭성종양의 양성과 악성",
        "text": "양성 낭성종양은 {{c1::얇고 매끈한 벽과 얇은 격막}}을 보인다.<br>악성을 시사하는 핵심은 {{c1::조영되는 고형 성분}} 또는 {{c1::불규칙하고 두꺼운 벽과 격막}}이며 종괴의 크기 자체는 핵심 기준이 아니다.",
        "extra": "크기보다 형태를 본다. 작은 병변이라도 불규칙한 조영 고형부가 있으면 악성을 생각한다.",
        "apps": ["난소 낭성종양", "양성/악성/점액성"],
    },
    {
        "deck": "6. 난소종양",
        "title": "난소 점액성 종양",
        "text": "난소 점액성 종양은 흔히 {{c1::다격막성}}이며, 방마다 점액 농도가 달라 서로 다른 신호를 보이는 {{c1::스테인드 글라스 모양}}이 특징적이다.",
        "extra": "여러 방의 밝기가 서로 다르다는 의미다. 이 소견은 점액성 계열을 시사하지만 양성과 악성은 벽과 고형부로 따로 판단한다.",
        "apps": [],
    },
    {
        "deck": "6. 난소종양",
        "title": "난소기형종",
        "text": "난소기형종에서 가장 중요한 영상 단서는 {{c1::지방 확인}}이다.<br>CT에서는 지방 감쇠를 보이고, MRI에서는 T1 고신호가 {{c1::지방억제 영상에서 감소}}한다.",
        "extra": "종괴의 크기보다 내부 지방 성분을 찾는 것이 중요하다. 출혈도 T1에서 밝을 수 있으므로 지방억제 전후를 비교한다.",
        "apps": ["난소기형종", "ct와 지방억제", "지방 확인"],
    },
    {
        "deck": "6. 난소종양",
        "title": "T1 고신호 난소병변의 지방과 혈액",
        "text": "T1 고신호 난소병변에서 지방억제 후 신호가 {{c1::감소하면 난소기형종}}, 고신호가 {{c1::유지되면 혈액을 포함한 자궁내막증}}을 우선 생각한다.",
        "extra": "2026년 족보가 직접 물은 감별이다. 처음부터 병명을 외우기보다 지방억제 후 신호가 사라지는지 먼저 확인한다.",
        "apps": ["기형종과 자궁내막증", "지방과 혈액"],
    },
    {
        "deck": "7. 부속기 비종양성 및 응급질환",
        "title": "난관난소농양",
        "text": "난관난소농양은 {{c1::두껍고 불규칙한 벽을 가진 부속기 낭성종괴}}로 보이며, 염증 때문에 주변에 {{c1::침윤}}이 동반된다.<br>관 모양의 두꺼운 벽 낭성병변은 난관염이나 고름난관을 시사한다.",
        "extra": "병변 자체도 지저분하고 주변도 지저분하다는 그림을 기억한다. 악성 낭성종양과 달리 염증성 침윤이 함께 보이는 맥락이 중요하다.",
        "apps": ["toa/pyosalpinx", "부속기 염증"],
    },
    {
        "deck": "7. 부속기 비종양성 및 응급질환",
        "title": "자궁내막증",
        "text": "자궁내막증은 {{c1::기능성 자궁내막조직이 자궁 밖에 존재}}하여 월경주기에 따라 반복 출혈하는 질환이다.<br>초음파에서는 내부의 {{c1::저수준 에코}}, MRI에서는 {{c1::T1 고신호와 다양한 T2 신호}}를 보인다.",
        "extra": "T2 신호가 다양한 이유는 출혈 시점과 혈액 상태가 서로 다르기 때문이다. 단순 낭종이 아니라 반복 출혈을 영상으로 보는 질환이다.",
        "apps": ["자궁내막증"],
    },
    {
        "deck": "7. 부속기 비종양성 및 응급질환",
        "title": "난관임신",
        "text": "자궁외임신의 약 {{c1::95퍼센트는 난관임신}}이다.<br>부속기에 {{c1::두껍고 강하게 조영되는 테두리의 낭성병변}}이 보이고, 파열되면 {{c1::혈복강}}이 동반될 수 있다.<br>병변과 별도로 같은 쪽의 정상 난소가 확인되는 것이 중요한 단서다.",
        "extra": "정상 난소가 따로 보이면서 그 옆에 조영되는 낭성병변이 있으면 난소 병변보다 난관 병변을 생각한다.",
        "apps": [],
    },
    {
        "deck": "7. 부속기 비종양성 및 응급질환",
        "title": "난소꼬임",
        "text": "난소꼬임의 주요 영상소견은 {{c1::꼬임매듭 또는 소용돌이}}, {{c1::부속기 비후}}, 혈류 장애에 의한 {{c1::난소 조영 감소}}이다.",
        "extra": "꼬임으로 혈관이 눌리면 부종과 허혈이 생기고 조영이 감소한다. 종괴 동반 비율보다 직접 소견을 우선한다.",
        "apps": ["난관임신 vs 난소꼬임", "부속기 응급"],
    },
]


INF_CONCEPTS = [
    {
        "deck": "1. 정의와 정상임신",
        "title": "난임의 정의",
        "text": "세계보건기구는 난임을 {{c1::12개월 이상 피임하지 않고 규칙적인 성관계를 했음에도 임신되지 않는 상태}}로 정의한다.<br>미국생식의학회는 성공적인 임신에 도달하지 못한 경우와 공여 생식세포나 배아를 포함한 의학적 개입이 필요한 경우까지 포함한다.",
        "extra": "시험에서는 세계보건기구의 12개월 기준을 우선 기억한다. 여성과 남성 어느 쪽의 생식기관 문제도 난임 원인이 될 수 있다.",
        "apps": [],
    },
    {
        "deck": "1. 정의와 정상임신",
        "title": "Fecundability와 Fecundity",
        "text": "Fecundability는 {{c1::한 배란주기당 임신 가능성}}, fecundity는 {{c1::생아 출생 가능성}}을 뜻한다.<br>한 주기당 임신 가능성은 대략 20퍼센트이며 최대 약 35퍼센트를 넘지 않는다.",
        "extra": "한 번의 시도로 임신되지 않는 것은 정상 범위에서도 흔하다. 임신 가능성과 생아 출생 가능성을 구분한다.",
        "apps": [],
    },
    {
        "deck": "1. 정의와 정상임신",
        "title": "정상 임신 과정",
        "text": "정상 임신은 배란된 난자와 정자가 난관에서 수정된 뒤 {{c1::상실배}}, {{c1::배반포}}로 발달하여 자궁내막에 {{c1::착상}}하는 과정이다.",
        "extra": "수정과 초기 분할은 난관에서 진행되고 배반포 단계에서 자궁내막에 착상한다. 이 흐름의 어느 단계가 막히는지에 따라 난임 원인을 나눌 수 있다.",
        "apps": ["정상 임신"],
    },
    {
        "deck": "1. 정의와 정상임신",
        "title": "난임 원인의 큰 틀",
        "text": "난임 원인은 {{c1::남성 요인}}, {{c1::여성 요인}}, {{c1::남녀 복합 요인}}, {{c1::원인불명}}으로 나눈다.<br>실제 평가는 부부를 함께 대상으로 진행한다.",
        "extra": "산부인과 수업에서는 여성 요인을 더 자세히 배우지만 남성 검사를 먼저 또는 동시에 시행해야 한다.",
        "apps": [],
    },
    {
        "deck": "2. 초기 평가와 생활환경",
        "title": "난임 초기 평가",
        "text": "초기 평가는 {{c1::병력청취}}, 신체진찰, 비침습적 검사, 필요한 침습적 검사 순으로 진행한다.<br>병력에는 월경 및 산과력, 이전 검사와 치료, 내외과 질환, 성생활과 생활방식, 정서와 윤리적 고려사항이 포함된다.",
        "extra": "두 사람이 모두 임신을 원하는지와 치료를 어디까지 받아들일 수 있는지도 확인한다. 난임은 정서적 부담이 크므로 환자의 인식과 감정도 평가한다.",
        "apps": [],
    },
    {
        "deck": "2. 초기 평가와 생활환경",
        "title": "생활습관과 환경 요인",
        "text": "비만과 흡연, 대마 및 코카인, 과음, 복사열과 중금속 및 농약 노출은 {{c1::가임력을 감소}}시킬 수 있다.<br>비만은 여성의 월경장애와 남성의 정액 이상, 흡연과 과음은 용량이 많을수록 더 큰 영향을 줄 수 있다.",
        "extra": "세부 항목을 따로 외우기보다 남녀 생식기능과 임신 예후에 모두 영향을 줄 수 있다는 큰 틀을 잡는다.",
        "apps": [],
    },
    {
        "deck": "2. 초기 평가와 생활환경",
        "title": "연령에 따른 평가 시작 시점",
        "text": "여성이 35세 미만이면 {{c1::12개월}}, 35세 이상이면 {{c1::6개월}} 임신을 시도한 뒤 평가를 시작한다.<br>40세 초과 또는 위험요인이 있으면 {{c1::즉시 평가}}한다.",
        "extra": "위험요인에는 불규칙 월경, 자궁 및 난관과 복막질환, 알려진 남성요인, 성기능장애, 난소예비능 저하 위험이 포함된다.",
        "apps": ["세 커플", "평가 시작"],
    },
    {
        "deck": "3. 남성요인과 정액검사",
        "title": "남성 난임 원인의 큰 틀",
        "text": "대표적인 남성 원인은 {{c1::정계정맥류}}, 원인불명, 고환기능 이상, 성기능장애, 폐쇄, 면역요인이다.<br>원인과 관계없이 첫 비침습 검사는 {{c1::정액검사}}이다.",
        "extra": "정계정맥류는 고환 온도를 높여 정자생성을 방해할 수 있다. 남성요인의 결과는 대부분 정액검사 이상으로 나타난다.",
        "apps": [],
    },
    {
        "deck": "3. 남성요인과 정액검사",
        "title": "정액검사의 다섯 지표",
        "text": "정액검사는 {{c1::정액량}}, {{c1::정자농도}}, {{c1::총 운동성}}, {{c1::전진 운동성}}, {{c1::정상 형태 비율}}을 중심으로 본다.",
        "extra": "한 지표만으로 난임을 진단하지 않는다. 다섯 지표의 전체 패턴과 반복검사 결과를 함께 해석한다.",
        "apps": [],
    },
    {
        "deck": "3. 남성요인과 정액검사",
        "title": "2021 WHO 정액검사 참고 하한",
        "text": "정액량은 {{c1::1.4 mL 이상}}, 정자농도는 {{c1::1 mL당 1천6백만 이상}}, 총 운동성은 {{c1::42퍼센트 이상}}, 전진 운동성은 {{c1::30퍼센트 이상}}, 정상 형태는 {{c1::4퍼센트 이상}}이 참고 하한이다.",
        "extra": "이 수치는 정상과 난임을 절대적으로 가르는 값이 아니라 임신 가능성이 낮은 집단에서 얻은 참고 하한이다.",
        "apps": [],
    },
    {
        "deck": "3. 남성요인과 정액검사",
        "title": "정액검사 해석과 반복",
        "text": "개별 정액검사 수치 하나만으로 남성 난임을 진단하지 않는다.<br>이상 소견이 있으면 시간 간격을 두고 {{c1::적어도 두 번 검사}}하여 재확인한다.",
        "extra": "정액검사 결과는 변동성이 크다. 발열, 금욕기간, 검체 손실과 운반 조건도 결과에 영향을 줄 수 있다.",
        "apps": [],
    },
    {
        "deck": "3. 남성요인과 정액검사",
        "title": "정액 검체 채취와 관리",
        "text": "정액검사 전 금욕기간은 {{c1::2일에서 7일}}, 채취한 검체는 가능하면 {{c1::30분 이내}} 분석하며 {{c1::20도에서 37도}}로 유지한다.<br>정자가 많은 첫 분획이 소실되면 반드시 보고한다.",
        "extra": "검체 일부가 빠지면 실제보다 정자농도가 낮게 측정될 수 있다. 채취와 운반 조건도 검사 결과의 일부다.",
        "apps": [],
    },
    {
        "deck": "3. 남성요인과 정액검사",
        "title": "Azoospermia와 Aspermia",
        "text": "Azoospermia는 {{c1::정액은 나오지만 정자가 없는 상태}}, aspermia는 {{c1::사정액 자체가 나오지 않는 상태}}이다.",
        "extra": "두 용어는 비슷해 보이지만 문제의 위치가 다르다. 정액 유무와 정자 유무를 따로 본다.",
        "apps": [],
    },
    {
        "deck": "3. 남성요인과 정액검사",
        "title": "무정자증의 위치 분류",
        "text": "고환 전 무정자증은 {{c1::성선자극호르몬 부족으로 정자생성이 일어나지 않는 상태}}, 고환성 무정자증은 {{c1::고환 자체의 기능부전}}, 고환 후 무정자증은 {{c1::폐쇄 또는 역행성 사정}}이 원인이다.",
        "extra": "고환 후 원인은 정자를 만들 수 있으므로 수술적으로 정자를 채취할 수 있다. 고환 자체 기능부전은 정자생성 가능성을 별도로 평가해야 한다.",
        "apps": [],
    },
    {
        "deck": "4. 연령과 난소예비능",
        "title": "난소예비능",
        "text": "난소예비능은 특정 시점에 남아 있는 {{c1::난포군과 난소자극에 대한 반응}}을 추정하는 개념이다.<br>자연 임신 가능성이나 폐경 시점을 직접 예측하는 검사는 아니다.",
        "extra": "난소예비능 검사는 난임 환자에서 자극 반응을 예측하고 치료계획을 세우는 데 사용한다.",
        "apps": [],
    },
    {
        "deck": "4. 연령과 난소예비능",
        "title": "연령과 난포 소모",
        "text": "난포 수는 태아 20주 무렵 약 {{c1::600만에서 700만}}, 출생 시 {{c1::50만에서 200만}}, 사춘기 {{c1::30만에서 40만}}으로 감소한다.<br>여성 연령이 증가하면 가임력은 감소하고 유산 위험은 증가한다.",
        "extra": "난포의 소모는 정상적인 생리 과정이다. 개인별 속도는 유전과 환경, 생활습관에 따라 다르며 어떤 검사도 생식수명을 정확히 예측하지 못한다.",
        "apps": [],
    },
    {
        "deck": "4. 연령과 난소예비능",
        "title": "AMH",
        "text": "항뮐러관호르몬은 작은 전동난포와 동난포의 {{c1::과립막세포}}에서 분비되며 월경주기의 영향을 적게 받아 {{c1::주기와 관계없이}} 측정할 수 있다.",
        "extra": "AMH는 난소자극 반응을 예측하는 데 유용하지만 난임 병력이 없는 여성의 자연 임신 가능성을 직접 나타내지는 않는다.",
        "apps": [],
    },
    {
        "deck": "4. 연령과 난소예비능",
        "title": "AFC",
        "text": "동난포수는 초기 난포기에 양쪽 난소의 {{c1::2 mm에서 10 mm 크기 난포}}를 모두 세는 검사이다.<br>{{c1::4개 미만}}이면 불량한 난소자극 반응을 예상한다.",
        "extra": "한쪽 난소만 세는 것이 아니라 양쪽 난소의 난포 수를 합한다. 초음파 이미지에서 작은 검은 원들을 직접 세는 검사다.",
        "apps": ["antral follicle", "afc 영상"],
    },
    {
        "deck": "4. 연령과 난소예비능",
        "title": "AMH와 난소자극 반응",
        "text": "AMH가 {{c1::1 ng/mL 미만}}이면 불량한 난소반응, {{c1::3.5 ng/mL 초과}}이면 과반응 가능성이 높다.",
        "extra": "이 수치는 난소자극 약물의 용량과 과반응 위험을 판단하는 데 사용한다. 낮은 AMH만으로 자연 임신이 불가능하다고 말하지 않는다.",
        "apps": [],
    },
    {
        "deck": "4. 연령과 난소예비능",
        "title": "기저 FSH와 Estradiol",
        "text": "월경주기 2일에서 4일의 FSH가 {{c1::10 IU/L 초과}}하면 저반응을 예상한다.<br>기저 FSH가 정상이더라도 월경주기 3일의 estradiol이 {{c1::60에서 80 pg/mL 초과}}하면 저반응을 시사할 수 있다.",
        "extra": "MCD는 menstrual cycle day, 즉 월경주기일을 뜻한다. 두 검사는 초기 난포기에 측정한다.",
        "apps": [],
    },
    {
        "deck": "4. 연령과 난소예비능",
        "title": "난소예비능 평가법 지도",
        "text": "난소예비능은 {{c1::AMH, AFC, 기저 FSH, 기저 estradiol, clomiphene citrate challenge test, inhibin B}}로 평가할 수 있다.<br>난소 용적은 이 강의와 반복 족보에서 표준 평가법으로 제시되지 않았다.",
        "extra": "족보는 평가법 목록에서 하나를 제외하는 형태로 반복된다. 먼저 전체 목록을 한 장으로 잡고 각 검사의 기준을 연결한다.",
        "apps": [],
    },
    {
        "deck": "5. 여성요인과 배란평가",
        "title": "여성 난임 원인의 분포",
        "text": "여성 난임 원인 중 배란요인은 {{c1::30퍼센트에서 40퍼센트}}, 난관요인은 {{c1::25퍼센트에서 35퍼센트}}, 자궁요인은 약 {{c1::15퍼센트}}를 차지한다.",
        "extra": "정확한 수치보다 배란요인과 난관요인이 가장 큰 비중을 차지한다는 순서를 기억한다.",
        "apps": [],
    },
    {
        "deck": "5. 여성요인과 배란평가",
        "title": "배란장애의 월경 양상",
        "text": "희발월경과 무월경, 빈발월경은 배란장애를 시사한다.<br>다만 규칙적인 월경 여성에서도 {{c1::1퍼센트에서 14퍼센트}}에서 무배란이 발생할 수 있다.",
        "extra": "월경이 규칙적이라는 사실만으로 배란을 완전히 확정하지 않는다. 필요하면 배란 확인 검사를 시행한다.",
        "apps": [],
    },
    {
        "deck": "5. 여성요인과 배란평가",
        "title": "기초체온으로 배란 확인",
        "text": "배란 후 progesterone의 영향으로 기초체온이 {{c1::0.3도에서 0.6도 상승}}하고 이 상승이 {{c1::3일 이상 지속}}되는 이중상 패턴을 보인다.",
        "extra": "기초체온은 이미 일어난 배란을 추정할 뿐 사전에 예측하지 못한다. 생활조건에 영향을 많이 받아 위음성이 흔하다.",
        "apps": ["기초체온"],
    },
    {
        "deck": "5. 여성요인과 배란평가",
        "title": "자궁경부 점액과 소변 LH",
        "text": "자궁경부 점액은 배란 2일에서 3일 전에 양이 많고 잘 늘어난다.<br>소변 LH 검사는 {{c1::LH 급증을 검출}}하며 양성 후 약 {{c1::14시간에서 26시간}} 뒤 배란을 예상한다.",
        "extra": "월경이 불규칙하거나 다낭난소증후군처럼 기저 LH가 높은 경우 소변 LH 검사의 해석이 어렵다.",
        "apps": ["자궁경부 점액", "소변 lh", "cervical mucus"],
    },
    {
        "deck": "5. 여성요인과 배란평가",
        "title": "Progesterone과 초음파로 배란 확인",
        "text": "다음 월경 7일 전 또는 LH 급증 7일 후 측정한 혈청 progesterone이 {{c1::3 ng/mL 초과}}이면 배란을 지지한다.<br>질초음파에서는 추적하던 난포의 {{c1::크기 감소와 더글라스와 액체}}를 확인한다.",
        "extra": "고정된 월경주기 21일보다 다음 월경과 LH 급증을 기준으로 측정 시점을 잡는 것이 현재 강의의 설명이다.",
        "apps": [],
    },
    {
        "deck": "6. 난관요인",
        "title": "난관요인의 원인",
        "text": "난관요인은 감염성과 비감염성으로 나눈다.<br>감염성 원인은 골반염과 난관염이 중심이며, 비감염성 원인에는 {{c1::골반유착, 난관 자궁내막증, 난관폴립, 난관경련, 관내 점액과 잔여물}}이 있다.",
        "extra": "난관이 막히거나 움직임이 떨어지면 정자와 난자의 이동, 수정란의 이동이 방해된다.",
        "apps": [],
    },
    {
        "deck": "6. 난관요인",
        "title": "반복 골반염과 난관 손상",
        "text": "골반염을 1회, 2회, 3회 경험한 뒤 난관염 위험은 각각 약 {{c1::8퍼센트, 19퍼센트, 40퍼센트}}로 증가한다.",
        "extra": "반복 감염은 유착과 폐쇄를 누적시킨다. 수치보다 반복될수록 위험이 크게 증가한다는 방향성을 먼저 기억한다.",
        "apps": [],
    },
    {
        "deck": "6. 난관요인",
        "title": "자궁난관조영술",
        "text": "자궁난관조영술은 {{c1::난관 개통성을 확인하는 기본 검사}}이며 월경주기 {{c1::5일에서 12일}}에 시행한다.<br>현재 골반염과 조영제 반응 병력은 금기다.",
        "extra": "정상에서는 조영제가 양쪽 난관을 지나 복강으로 퍼진다. 원위부가 막히면 난관이 팽창하고 복강 내 유출이 보이지 않는다.",
        "apps": ["hsg", "원위부 난관폐쇄", "자궁난관조영술"],
    },
    {
        "deck": "6. 난관요인",
        "title": "복강경과 HyCoSy",
        "text": "복강경은 난관과 복막을 직접 관찰하여 {{c1::유착과 자궁내막증을 진단하고 동시에 치료}}할 수 있다.<br>HyCoSy는 초음파 조영제를 이용해 {{c1::난관 개통성}}을 평가한다.",
        "extra": "복강경은 정확하지만 침습적이므로 다른 수술적 적응증이 있을 때 함께 시행한다. 기본 검사로는 자궁난관조영술을 우선 기억한다.",
        "apps": [],
    },
    {
        "deck": "6. 난관요인",
        "title": "난관수종",
        "text": "난관수종의 액체는 {{c1::자궁내막 수용성을 낮추고 배아독성}}을 나타낼 수 있다.<br>체외수정 임신율을 약 {{c1::50퍼센트 감소}}시키므로 체외수정 전에 {{c1::난관절제술}}을 시행하면 임신율과 생아출생률이 높아진다.",
        "extra": "난관절제 후 자연적인 난자 이동은 어렵기 때문에 난관수종을 제거한 뒤 체외수정을 진행하는 흐름으로 이해한다.",
        "apps": ["hydrosalpinx", "난관수종"],
    },
    {
        "deck": "7. 자궁요인과 자궁내막증",
        "title": "자궁요인의 큰 틀",
        "text": "자궁강의 폴립과 과증식, 점막밑근종, 자궁강 유착, 선천기형은 {{c1::착상 공간을 변형}}하여 난임을 일으킬 수 있다.",
        "extra": "진단은 자궁강의 형태와 병변을 확인하는 방향으로 진행하고, 치료는 병변을 제거해 정상 공간을 회복하는 것이 중심이다.",
        "apps": [],
    },
    {
        "deck": "7. 자궁요인과 자궁내막증",
        "title": "자궁경검사",
        "text": "자궁경검사는 {{c1::자궁강 평가의 표준 검사}}이며 자궁내막이 얇은 {{c1::초기 또는 중기 난포기}}에 시행한다.",
        "extra": "자궁강을 직접 보면서 폴립과 근종, 유착을 진단하고 필요한 경우 동시에 제거할 수 있다.",
        "apps": [],
    },
    {
        "deck": "7. 자궁요인과 자궁내막증",
        "title": "식염수주입초음파와 자궁강 유착",
        "text": "식염수주입초음파는 자궁강에 식염수를 넣어 공간을 벌린 뒤 병변을 본다.<br>자궁강을 가로지르는 {{c1::띠나 기둥 모양 구조}}는 자궁강 유착을 시사하고, 폴립과 점막밑근종은 {{c1::국소 종괴}}로 보인다.",
        "extra": "식염수가 채운 검은 공간 안에서 유착은 다리처럼 가로지르고 종괴는 한쪽에서 공간을 채운다.",
        "apps": ["sis", "자궁강 유착", "식염수"],
    },
    {
        "deck": "7. 자궁요인과 자궁내막증",
        "title": "자궁요인의 치료",
        "text": "점막밑근종은 {{c1::근종절제술 또는 자궁경 제거}}, 자궁강 유착은 {{c1::자궁경 유착박리 후 재유착 방지를 위한 estrogen 치료}}를 시행한다.",
        "extra": "자궁강 유착은 소파술 뒤에 발생할 수 있고 치료 과정에서도 다시 유착될 수 있으므로 재발 방지가 중요하다.",
        "apps": [],
    },
    {
        "deck": "7. 자궁요인과 자궁내막증",
        "title": "자궁내막증이 난임을 일으키는 기전",
        "text": "자궁내막증은 반복 염증으로 {{c1::유착과 섬유화에 의한 골반 해부학적 변형}}을 만들고, 만성염증이 {{c1::생식세포와 배아, 난관채, 자궁내막 기능}}을 방해한다.",
        "extra": "기계적 변형과 염증성 환경이라는 두 축으로 정리한다.",
        "apps": [],
    },
    {
        "deck": "7. 자궁요인과 자궁내막증",
        "title": "자궁내막증과 임신 예후",
        "text": "자궁내막증 환자의 주기당 임신 가능성은 약 {{c1::2퍼센트에서 10퍼센트}}로 추정된다.<br>복강경 병기 III에서 IV 또는 이전 수술력이 있으면 임신율과 생아출생률이 감소한다.",
        "extra": "증상의 정도와 병기가 항상 일치하지는 않지만 중증 병기와 수술력은 난임 예후와 관련된다.",
        "apps": [],
    },
    {
        "deck": "8. 치료와 배란유도 및 IUI",
        "title": "난임치료의 세 대표 방법",
        "text": "강의에서 제시한 대표 치료는 {{c1::배란유도}}, {{c1::자궁강내 인공수정}}, {{c1::체외수정}}이다.<br>모든 환자가 같은 순서를 반드시 거치는 것은 아니며 원인과 연령에 따라 적절한 치료부터 선택한다.",
        "extra": "난관폐쇄나 심한 남성요인처럼 처음부터 체외수정이 필요한 경우도 있다.",
        "apps": [],
    },
    {
        "deck": "8. 치료와 배란유도 및 IUI",
        "title": "가임 창",
        "text": "가임 창은 {{c1::배란일을 마지막 날로 하는 6일}}이다.<br>정자는 에스트로겐 영향을 받은 자궁경부 점액에서 최대 약 6일 생존하고, 난자는 배란 후 {{c1::12시간에서 24시간}} 수정될 수 있다.",
        "extra": "난자의 생존 시간이 짧기 때문에 정자가 먼저 들어와 기다리는 시기를 포함한다.",
        "apps": [],
    },
    {
        "deck": "8. 치료와 배란유도 및 IUI",
        "title": "배란유도의 적용 조건",
        "text": "배란유도는 {{c1::배란장애}}가 있고 약물 자극에 반응할 수 있는 HPO 축이 유지된 환자에게 시행한다.<br>정상 성생활이 가능하고 정액검사와 난관 및 자궁 상태가 임신을 허용해야 한다.",
        "extra": "HPO 축은 시상하부, 뇌하수체, 난소 축을 뜻한다. 여성의 배란만 유도하는 치료이므로 정자와 난관이 정상이어야 한다.",
        "apps": [],
    },
    {
        "deck": "8. 치료와 배란유도 및 IUI",
        "title": "배란장애 원인별 치료",
        "text": "다낭난소증후군은 생활습관 교정과 체중감량 후 {{c1::letrozole 또는 clomiphene}}, 고프로락틴혈증은 {{c1::dopamine agonist}}, 갑상선기능저하는 {{c1::levothyroxine}}으로 치료한다.",
        "extra": "배란장애의 원인을 먼저 교정한다. 최근에는 반감기가 짧고 다태임신 위험이 낮은 letrozole을 더 흔히 사용한다.",
        "apps": [],
    },
    {
        "deck": "8. 치료와 배란유도 및 IUI",
        "title": "Clomiphene과 Letrozole",
        "text": "Clomiphene은 시상하부의 {{c1::estrogen receptor를 차단}}하여 성선자극호르몬 분비를 늘리고 반감기는 약 {{c1::2주}}이다.<br>Letrozole은 {{c1::aromatase inhibitor}}로 estradiol을 낮추며 반감기는 약 {{c1::48시간}}이다.",
        "extra": "두 약 모두 뇌가 estrogen이 부족하다고 느끼게 해 FSH와 LH 분비를 높인다. Letrozole은 반감기가 짧고 다태임신률이 낮다.",
        "apps": [],
    },
    {
        "deck": "8. 치료와 배란유도 및 IUI",
        "title": "배란유도 일정",
        "text": "배란유도 약제는 월경주기 {{c1::3일에서 5일}}에 시작하여 {{c1::5일간}} 투여한다.<br>초음파로 우성난포의 성장과 배란을 확인하며 총 {{c1::6주기에서 12주기}}를 넘기지 않는다.",
        "extra": "여성 연령이 증가하면 가임력이 감소하므로 효과가 없을 때 같은 치료를 무기한 반복하지 않고 다음 단계로 넘어간다.",
        "apps": [],
    },
    {
        "deck": "8. 치료와 배란유도 및 IUI",
        "title": "자궁강내 인공수정",
        "text": "자궁강내 인공수정은 배란 시기에 {{c1::세척하고 선별한 정자를 자궁강 안에 주입}}하는 치료다.<br>난관과 자궁이 정상이고 정상 성생활이 어렵거나 경증 정자감소증이 있을 때 고려하며 배란유도를 함께 시행할 수 있다.",
        "extra": "IUI는 intrauterine insemination의 약자다. 정자가 이동해야 하므로 적어도 한쪽 난관이 열려 있어야 한다.",
        "apps": ["iui", "인공수정"],
    },
    {
        "deck": "9. 난임 증가의 배경",
        "title": "난임 환자가 증가하는 배경",
        "text": "혼인과 첫 출산 연령이 높아지는 동안 인간의 생물학적 가임력은 변하지 않았다.<br>여성 연령 증가에 따른 {{c1::난소예비능과 난자 질의 감소}}, 사회적 및 경제적 요인, 생활환경 변화가 난임 환자와 시술 건수 증가에 영향을 준다.",
        "extra": "공식 학습성과에 포함된 내용이다. 사회적 선택을 평가하기보다 출산 시기와 생물학적 가임력의 불일치를 이해한다.",
        "apps": [],
    },
]


def rebuild(src, out, kind, concepts):
    work = OUTPUT / f"{kind}_work"
    db = extract_apkg(src, work)
    con = sqlite3.connect(db)
    con.create_collation("unicase", collation)
    cur = con.cursor()
    cur.execute("pragma journal_mode=DELETE")
    now = int(time.time())
    names, field_map, cloze_mid, basic_mid, jokbo_mid = model_info(cur)
    original_mids = dict(cur.execute("select id,mid from notes"))
    before_notes = cur.execute("select count(*) from notes").fetchone()[0]
    before_cards = cur.execute("select count(*) from cards").fetchone()[0]
    decks = deck_names(cur)
    jbl_parent_did, jbl_parent_name = find_parent(decks, "2. JBL")
    jokbo_parent_did, jokbo_parent_name = find_parent(decks, "3. 족보")
    reserved = set(decks)
    optional_name = jbl_parent_name + SEP + ("8. 보충 개념" if kind == "gyne" else "10. 보충 개념")
    optional_did = ensure_deck(cur, optional_name, jbl_parent_did, now, reserved)
    app_name = jbl_parent_name + SEP + ("9. 영상 적용" if kind == "gyne" else "11. 사례와 영상 적용")
    app_did = ensure_deck(cur, app_name, jbl_parent_did, now, reserved)
    topic_dids = {}
    for spec in concepts:
        label = spec["deck"]
        if label not in topic_dids:
            topic_dids[label] = ensure_deck(cur, jbl_parent_name + SEP + label, jbl_parent_did, now, reserved)
    direct_jokbo_did = ensure_deck(cur, jokbo_parent_name + SEP + "1. 핵심 족보", jokbo_parent_did, now, reserved)
    legacy_jokbo_did = ensure_deck(cur, jokbo_parent_name + SEP + "2. 구족보 참고", jokbo_parent_did, now, reserved)

    jbl_dids = [did for did, name in decks.items() if jbl_parent_name in name]
    if jbl_parent_did not in jbl_dids:
        jbl_dids.append(jbl_parent_did)
    q = ",".join("?" for _ in jbl_dids)
    cur.execute(f"update cards set did=?,queue=-1,mod=?,usn=-1 where did in ({q})", [optional_did, now, *jbl_dids])

    candidates = []
    for nid, mid, flds, tags in cur.execute("select id,mid,flds,tags from notes"):
        crows = cur.execute("select id,did from cards where nid=?", (nid,)).fetchall()
        if not crows or mid != basic_mid:
            continue
        if not any(did in jbl_dids for _, did in crows):
            continue
        vals = flds.split(SEP)
        front = vals[0] if vals else ""
        if "atlas" in (tags or "").casefold() or "참고용 이미지 atlas" in normalize_title(front):
            continue
        candidates.append({
            "nid": nid,
            "title": normalize_title(front),
            "fields": vals,
            "cards": [cid for cid, _ in crows],
            "kind": kind,
        })

    state = {"next_id": max(cur.execute("select max(id) from notes").fetchone()[0] or 0, cur.execute("select max(id) from cards").fetchone()[0] or 0) + 1000}
    due = 1
    used = set()
    new_nids = []
    active_apps = []
    for spec in concepts:
        did = topic_dids[spec["deck"]]
        cid, nid = insert_cloze(
            cur, state, cloze_mid, field_map[cloze_mid], did, due,
            spec["title"], spec["text"], spec["extra"],
            ("gynecologic-imaging" if kind == "gyne" else "infertility") + " concept cloze concept_first",
            now,
        )
        new_nids.append(nid)
        due += 1
        due, activated = activate_matching_app(cur, candidates, used, spec.get("apps", []), did, due, now)
        active_apps.extend(activated)

    for item in candidates:
        if item["nid"] in used:
            continue
        joined = " ".join(item["fields"])
        if "<img" not in joined.casefold():
            continue
        used.add(item["nid"])
        vals = [clean_symbols(v) for v in item["fields"]]
        set_note_fields(cur, item["nid"], vals, ("gynecologic-imaging" if kind == "gyne" else "infertility") + " application image_review", now)
        for cid in item["cards"]:
            cur.execute("update cards set did=?,type=0,queue=0,due=?,ivl=0,factor=0,reps=0,lapses=0,left=0,odue=0,odid=0,mod=?,usn=-1 where id=?", (app_did, due, now, cid))
            due += 1
            active_apps.append(cid)

    jokbo_dids = [did for did, name in deck_names(cur).items() if jokbo_parent_name in name]
    jokbo_rows = []
    for nid, mid, flds in cur.execute("select id,mid,flds from notes where mid=?", (jokbo_mid,)):
        cards = cur.execute("select id,did from cards where nid=?", (nid,)).fetchall()
        if not cards or not any(did in jokbo_dids or did in {direct_jokbo_did, legacy_jokbo_did} for _, did in cards):
            continue
        vals = flds.split(SEP)
        code = strip_html(vals[0] if vals else "")
        body = " ".join(vals)
        low = strip_html(body).casefold()
        if kind == "gyne":
            legacy = any(k in low for k in ["hsg", "자궁난관조영", "uterine synechia", "hydrosalpinx", "tubal occlusion", "bicornuate"])
        else:
            legacy = any(k in low for k in ["postcoital", "pct", "luteal phase defect", "hamster", "ohss", "gnrh antagonist", "gift", "zift", "endometrial biopsy"])
        target = legacy_jokbo_did if legacy else direct_jokbo_did
        rewrite_jokbo(cur, nid, field_map[jokbo_mid], kind, now)
        for cid, _ in cards:
            cur.execute("update cards set did=?,type=0,queue=?,due=?,ivl=0,factor=0,reps=0,lapses=0,left=0,odue=0,odid=0,mod=?,usn=-1 where id=?", (target, -1 if legacy else 0, 0, now, cid))
        jokbo_rows.append((nid, target, legacy, code))

    direct_due = 1
    for nid, target, legacy, code in sorted(jokbo_rows, key=lambda row: row[3], reverse=True):
        if legacy:
            continue
        for cid, in cur.execute("select id from cards where nid=? order by ord", (nid,)):
            cur.execute("update cards set due=? where id=?", (direct_due, cid))
            direct_due += 1

    cur.execute("update col set mod=?,scm=?", (int(time.time() * 1000), int(time.time() * 1000)))
    con.commit()
    integrity = cur.execute("pragma integrity_check").fetchone()[0]
    changed_mids = [nid for nid, mid in original_mids.items() if cur.execute("select mid from notes where id=?", (nid,)).fetchone()[0] != mid]
    active_jbl = cur.execute("select count(*) from cards c join decks d on c.did=d.id where d.name like ? and c.queue>=0", (jbl_parent_name + "%",)).fetchone()[0]
    active_due = [r[0] for r in cur.execute("select c.due from cards c join decks d on c.did=d.id where d.name like ? and c.queue>=0 order by c.due", (jbl_parent_name + "%",))]
    due_ok = active_due == list(range(1, len(active_due) + 1))
    active_text = "\n".join(r[0] for r in cur.execute("select n.flds from notes n join cards c on n.id=c.nid join decks d on c.did=d.id where d.name like ? and c.queue>=0", (jbl_parent_name + "%",)))
    bad_symbols = {s: active_text.count(s) for s in ["•", "·", "→", "⇒"] if s in active_text}
    media = json.load(open(work / "media", encoding="utf-8")) if (work / "media").exists() else {}
    media_names = set(media.values())
    referenced = set()
    for flds, in cur.execute("select flds from notes"):
        referenced.update(re.findall(r'<img[^>]+src=["\']([^"\']+)', flds))
    missing_media = sorted(name for name in referenced if name not in media_names)
    after_notes = cur.execute("select count(*) from notes").fetchone()[0]
    after_cards = cur.execute("select count(*) from cards").fetchone()[0]
    expected = expected_check(cur, [
        "26-출산및생식의학-51", "26-출산및생식의학-52", "23-출산및생식의학-81",
        "22-출산및생식의학-89", "20-산과-102", "19-산과-104", "18-출산및생식의학-71",
        "17-출산및생식의학-75", "16-산과-113", "16-산과-주관식 38", "15-산과-객121",
    ] if kind == "gyne" else ["26-연계-74", "26-연계-75", "26-연계-89"])
    con.commit()
    con.close()
    for extra in [work / "collection.anki2-wal", work / "collection.anki2-shm"]:
        if extra.exists():
            extra.unlink()
    repack(work, out)
    return {
        "kind": kind,
        "before_notes": before_notes,
        "before_cards": before_cards,
        "after_notes": after_notes,
        "after_cards": after_cards,
        "new_concepts": len(new_nids),
        "active_app_cards": len(active_apps),
        "active_jbl": active_jbl,
        "active_jokbo": sum(1 for _, _, legacy, _ in jokbo_rows if not legacy),
        "legacy_jokbo": sum(1 for _, _, legacy, _ in jokbo_rows if legacy),
        "integrity": integrity,
        "changed_existing_note_types": len(changed_mids),
        "due_sequence_ok": due_ok,
        "bad_symbols": bad_symbols,
        "missing_media": missing_media,
        "expected_jokbo": expected,
        "output_size": out.stat().st_size,
    }


def main():
    refs = {
        "이원재 참고덱": inspect_reference(LEE_WONJAE),
        "이상훈 참고덱": inspect_reference(LEE_SANGHOON),
    }
    gyne = rebuild(GYNE_SRC, GYNE_OUT, "gyne", GYNE_CONCEPTS)
    inf = rebuild(INF_SRC, INF_OUT, "infertility", INF_CONCEPTS)
    lines = []
    lines.append("두 덱 개념 선행형 최종 검증")
    lines.append("")
    for name, data in refs.items():
        lines.append(f"{name}: notes={data[0]}, cards={data[1]}")
        for sample in data[2]:
            lines.append(f"  sample: {sample}")
    for result in [gyne, inf]:
        lines.append("")
        lines.append(f"[{result['kind']}]")
        for key, val in result.items():
            if key != "kind":
                lines.append(f"{key}: {val}")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))
    failures = []
    for result in [gyne, inf]:
        if result["integrity"] != "ok": failures.append(f"{result['kind']}: integrity")
        if result["changed_existing_note_types"] != 0: failures.append(f"{result['kind']}: note type changed")
        if not result["due_sequence_ok"]: failures.append(f"{result['kind']}: due sequence")
        if result["bad_symbols"]: failures.append(f"{result['kind']}: special symbols")
        if result["missing_media"]: failures.append(f"{result['kind']}: missing media")
        if not all(result["expected_jokbo"].values()): failures.append(f"{result['kind']}: missing expected jokbo")
    if failures:
        raise SystemExit("Validation failed: " + ", ".join(failures))


if __name__ == "__main__":
    main()
