from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import genanki
import gdown
import requests
import zstandard as zstd

# -----------------------------------------------------------------------------
# Compatibility and source loading
# -----------------------------------------------------------------------------
if not hasattr(genanki.Model, "STANDARD"):
    genanki.Model.STANDARD = genanki.Model.FRONT_BACK

_original_download = gdown.download


def _valid_payload(data: bytes, output: str | None) -> bool:
    suffix = Path(output or "").suffix.lower()
    if suffix == ".pdf":
        return data.startswith(b"%PDF")
    if suffix == ".apkg":
        return data.startswith(b"PK")
    return len(data) > 1024


def _compatible_download(*args, **kwargs):
    kwargs.pop("fuzzy", None)
    file_id = kwargs.get("id")
    output = kwargs.get("output")
    if file_id and output:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
        }
        for url in (
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
            f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t",
            f"https://drive.google.com/uc?id={file_id}&export=download",
        ):
            try:
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=180)
                if response.ok and _valid_payload(response.content, output):
                    Path(output).write_bytes(response.content)
                    print(f"Downloaded {output}: {len(response.content):,} bytes")
                    return output
            except Exception as exc:
                print("Direct Drive download failed:", exc)
    return _original_download(*args, **kwargs)


gdown.download = _compatible_download

ROOT = Path(__file__).resolve().parents[1]
base_script = ROOT / "build_decks.py"
source = base_script.read_text(encoding="utf-8")


def replace_once(pattern: str, replacement: str, *, flags: int = 0, label: str = "patch") -> None:
    global source
    source, count = re.subn(pattern, replacement, source, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label} failed; matches={count}")


# Public build copies in the user's temporary shared workspace.
source = source.replace("1tpNLSvDcJUx0McmWiLpt8xTePeVJd1OB", "1TuyVdMJnBZEOX9YGvtIAYOT09EGHDD5E")
source = source.replace("1lbWoXqb_tleGdSRP0QIisHpXde4uFdkk", "1oYXMxzJfWii0mnNTaOXldAQ-BLfg9O-C")
source = source.replace("1iAdIOlAOVrMqXb15g-1xa8nylsjjrrPS", "1Qw2s4JtHiDEJ15I0Snq_nyGz3kzt8kw1")
for old_id in (
    "1BLh4HkPnUEpwVa-7AaZYhKrttNa2p363",
    "1fIC9_LN1Vac5qBMhdF9DB6WYLopAqxJv",
    "1iX31-Lv52dFqYvpOXTr5MkKmj2UbdvwW",
):
    source = source.replace(old_id, "1xxPDqykU17XaoBGcP24fBN_nW02vYybg")

# The new 74-page pediatric lecture supplies concept images. The existing
# summary appendix remains the bounded source for school/KMLE question panels.
replace_once(
    r"(PEDS_PDF = download_drive\([^\n]+\)\n)",
    r"\1PEDS_Q_PDF = download_drive(\"1raCcBgDpXgw3hnXSEjHnLjabkh2NgY6i\", SRC / \"peds_summary.pdf\")\n",
    label="insert pediatric question source",
)

# New, collision-free roots ensure that importing over an older broken build
# cannot keep cards in the previous deck assignment.
source = source.replace(
    'peds_root = "외과학 입문::3. 계통별 수술::소아외과 (소화기학) (박태진) by 이용화"',
    'peds_root = "외과학 입문::3. 계통별 수술::소아외과 (소화기학) (박태진) by 이용화 0826 최종검수"',
)
source = source.replace(
    'breast_root = "외과학 입문::3. 계통별 수술::유방영상학 1, 2 (최혜영) by 이용화"',
    'breast_root = "외과학 입문::3. 계통별 수술::유방영상학 1, 2 (최혜영) by 이용화 0826 최종검수"',
)
source = source.replace(
    "return genanki.guid_for(self.model.name, *self.fields)",
    'return genanki.guid_for("FINAL_V3_20260826", self.model.name, *self.fields)',
)

# -----------------------------------------------------------------------------
# Pediatric lecture crops from the newly uploaded original lecture PDF
# -----------------------------------------------------------------------------
new_peds_crop_block = r'''# Pediatric lecture images from the original 74-page lecture PDF.
peds_imgs: dict[str, str] = {}
peds_crop_specs = {
    "thermoregulation": (11, (0.02, 0.12, 0.98, 0.91)),
    "warming": (12, (0.02, 0.12, 0.98, 0.92)),
    "tgdc_concept": (18, (0.02, 0.12, 0.98, 0.92)),
    "sistrunk": (19, (0.02, 0.08, 0.98, 0.94)),
    "branchial_types": (20, (0.02, 0.10, 0.98, 0.92)),
    "branchial_photo": (29, (0.02, 0.04, 0.98, 0.94)),
    "lm": (31, (0.02, 0.04, 0.98, 0.94)),
    "lm_surgery": (35, (0.02, 0.04, 0.98, 0.94)),
    "nec": (40, (0.02, 0.04, 0.98, 0.94)),
    "nec_tx": (39, (0.02, 0.10, 0.98, 0.93)),
    "red_flags": (43, (0.02, 0.10, 0.98, 0.91)),
    "three_clues": (44, (0.02, 0.10, 0.98, 0.91)),
    "appendix_us": (48, (0.02, 0.08, 0.98, 0.93)),
    "appendix_ct": (49, (0.02, 0.04, 0.98, 0.94)),
    "serial_exam": (71, (0.02, 0.08, 0.98, 0.93)),
    "diagnostic_lap": (74, (0.02, 0.04, 0.98, 0.94)),
}
for key, (page, rect) in peds_crop_specs.items():
    peds_imgs[key] = add_media(render_crop(PEDS_PDF, page, rect, f"peds_{key}.png"))

# Pediatric question panels/images.'''
replace_once(
    r"# Pediatric lecture/summary images\..*?# Pediatric question panels/images\.",
    new_peds_crop_block,
    flags=re.DOTALL,
    label="replace pediatric crop block",
)

question_block_pattern = r"(# Pediatric question panels/images\.)(.*?)(# Recognition galleries for JBL backs\.)"
match = re.search(question_block_pattern, source, flags=re.DOTALL)
if not match:
    raise RuntimeError("Pediatric question crop block not found")
question_body = match.group(2).replace("PEDS_PDF", "PEDS_Q_PDF")
source = source[: match.start()] + match.group(1) + question_body + match.group(3) + source[match.end() :]

# -----------------------------------------------------------------------------
# Objective card wording: remove author/editor voice while preserving content
# -----------------------------------------------------------------------------
wording_replacements = {
    "<b>가져갈 한 줄</b>": "<b>핵심</b>",
    "KMLE의 복벽갈림증 문제도 질환명보다 노출된 장에서 생기는 열·수분 손실에 대한 초기 대응을 묻습니다.": "노출된 장은 열과 수분 손실을 크게 증가시키므로 보온과 수액 공급이 우선됩니다.",
    "아래는 같은 단서를 반복해서 물은 실제 KMLE 영상들입니다.": "관련 KMLE 영상에서는 정중 위치와 혀 움직임이 반복적으로 제시됩니다.",
    "강의에서는 세부 술기보다 병력에서 이 단서를 먼저 잡는 수준을 강조했습니다. 학교 족보에서 같은 단서가 실제 영상과 함께 반복되었습니다.": "통증 이동, 혈성 점액변, 담즙성 구토는 각각 충수염, 장중첩증, 중장염전의 대표적인 임상 단서입니다.",
    "현재 강의에서 직접 연결되는 범주는 갑상설관낭종, 새열기형, 림프관기형, 유피낭종입니다.": "대표적인 선천성 경부 병변에는 갑상설관낭종, 새열기형, 림프관기형, 유피낭종이 있습니다.",
    "강의 직접 핵심은 혈성 점액변으로 장중첩증을 알아보는 것입니다.": "주기적 복통과 혈성 점액변은 장중첩증을 시사합니다.",
    "담도폐쇄증 치료는 강의 범위 밖이고, 이 문제는 red flag 적용용입니다.": "황달, 회색 변, 작은 담낭과 보이지 않는 총담관이 진단 단서입니다.",
    "같은 왕족 단서의 반복입니다.": "정중 위치와 혀 움직임이 진단 단서입니다.",
    "이 문장은 2019~2022년에 반복 출제된 왕족입니다.": "2019~2022년 학교 시험에서 반복 출제되었습니다.",
    "아래는 실제로 출제된 모든 mammography 이미지 문제입니다. 연도는 달라도 '악성 소견 → 초음파 → 조직검사'라는 판단을 반복합니다.": "2019~2026년 학교 시험의 mammography 영상은 악성 소견을 확인한 뒤 초음파와 조직검사로 이어지는 판단을 반복합니다.",
    "2026 Q71은 강의 마지막 증례와 같은 악성 고형 종괴를 보여주고 Category 4C + 초음파 유도 core biopsy를 답으로 요구했습니다.": "2026 Q71에서는 불규칙한 고형 종괴를 Category 4C로 평가하고 초음파 유도 core biopsy를 선택합니다.",
    "기억할 경계는 2%와 95%입니다.": "악성 가능성의 주요 경계는 2%와 95%입니다.",
    "2026 Q73의 정답도 수술 전 범위와 다발성 평가였습니다.": "수술 전에는 병변의 범위, 다발성, 반대측 유방을 평가할 수 있습니다.",
    "2019 Q64는 강의 사진 그대로 시술명을 물었습니다.": "2019 Q64에서는 초음파 유도하 wire localization의 시술명을 물었습니다.",
}
for old, new in wording_replacements.items():
    source = source.replace(old, new)

# Replace the out-of-scope reference card with a lecture-grounded card.
replace_once(
    r'add_basic\(peds_ref,\n    "<b>연관 문제의 변주 단서</b>.*?\n\)\n',
    '''add_basic(peds_ref,
    "<b>재태연령과 출생체중</b><br><br>재태연령과 출생체중은 각각 무엇을 나타냅니까?",
    "재태연령은 장기 성숙도를, 출생체중은 몸의 크기를 나타냅니다. 두 축은 독립적이므로 만삭아도 자궁내성장지연이 있으면 저체중 출생아일 수 있습니다. Preterm은 재태연령 37주 미만입니다."
)\n''',
    flags=re.DOTALL,
    label="replace out-of-scope reference card",
)

# Include the diagnostic-laparoscopy image in the appendicitis reasoning card.
source = source.replace(
    'img_html(peds_imgs["serial_exam"], "반복 진찰과 영상")',
    'img_html(peds_imgs["serial_exam"], "애매한 영상 소견") + img_html(peds_imgs["diagnostic_lap"], "지속 증상에서 시행한 진단적 복강경")',
)

# -----------------------------------------------------------------------------
# Breast Imaging school-exam subdeck: 2019-2026, 20 actual school questions
# -----------------------------------------------------------------------------
replace_once(
    r'(breast_jbl = genanki\.Deck\([^\n]+\)\n)',
    r'\1breast_school = genanki.Deck(deterministic_id(breast_root+"::2. 족보"), breast_root+"::2. 족보")\n',
    label="create breast school deck",
)

breast_school_code = r'''
# ---------- Breast Imaging school exam deck ----------
def add_breast_exam(title: str, question: str, answer: str, explanation: str,
                    options: list[tuple[str, str]] | None = None,
                    image: str | None = None, core: str | None = None) -> None:
    front = f"<b>{title}</b><br><br>{question}"
    if image:
        front += img_html(image, title)
    add_exam(breast_school, front, exam_back(answer, explanation, options=options, takeaway=core))

add_breast_exam(
    "2026 연계-70", "다음의 유방 영상 진단 기법에 대한 설명 중 옳은 것은?<br>① 높은 에너지 X-ray가 유리하다.<br>② 초음파는 낭성과 고형 종괴를 감별하고 치밀유방의 촉지 종괴 평가에 유용하다.<br>③ MRI는 특이도가 가장 높아 조직검사를 대체한다.<br>④ MRI가 미세석회화 평가에 가장 유용하다.<br>⑤ 조직검사로 암이 진단되면 MRI는 필요하지 않다.",
    "②", "초음파는 낭성/고형 감별, 촉지 병변 확인, 조직검사 유도에 유용합니다.",
    [("①", "유방촬영술은 연부조직 대비를 위해 저에너지 X-ray를 사용합니다."), ("②", "옳습니다."), ("③", "MRI는 민감도가 높지만 특이도가 낮아 조직검사를 대체하지 못합니다."), ("④", "미세석회화는 유방촬영술이 가장 잘 평가합니다."), ("⑤", "MRI는 수술 전 범위와 다발성 평가에 사용될 수 있습니다.")],
    core="Mammography는 미세석회화, 초음파는 낭성/고형과 유도, MRI는 범위 평가에 강합니다."
)
add_breast_exam(
    "2026 연계-71", "43세 여성의 유방초음파 병변에 대한 적절한 BI-RADS 범주와 권고 사항은?<br>① Category 3—6개월 추적<br>② Category 4A—단기 추적<br>③ Category 4B—MRI<br>④ Category 4C—초음파 유도 core needle biopsy<br>⑤ Category 6—치료 없이 추적",
    "④", "불규칙한 고형 종괴는 높은 악성 가능성을 보여 Category 4C로 평가하며 조직검사가 필요합니다.",
    [("①", "Category 3은 양성 추정 소견에서 단기 추적합니다."), ("②", "Category 4는 추적이 아니라 조직검사가 원칙입니다."), ("③", "MRI는 조직학적 확진을 대신하지 않습니다."), ("④", "옳습니다."), ("⑤", "Category 6은 이미 조직학적으로 확진된 암입니다.")],
    image=breast_exam_imgs["2026_q71_us"], core="불규칙한 고형 종괴 + Category 4 이상 = 조직검사."
)
add_breast_exam(
    "2026 연계-72", "43세 여성의 유방촬영술에서 spiculated mass가 보인다. 옳은 설명은?<br>① 초음파 후 조직검사를 시행한다.<br>② Category 3이다.<br>③ 6개월 후 유방촬영술을 시행한다.<br>④ 실질 조성 유형 A이다.<br>⑤ MRI를 시행하면 조직검사를 생략할 수 있다.",
    "①", "Spiculated margin은 Category 4 또는 5에 해당하는 악성 의심 소견이므로 초음파와 조직검사가 필요합니다.",
    [("①", "옳습니다."), ("②", "Spiculated mass는 probably benign이 아닙니다."), ("③", "단기 추적 대상이 아닙니다."), ("④", "영상은 fatty breast로 볼 수 없습니다."), ("⑤", "MRI도 조직검사를 대체하지 못합니다.")],
    image=breast_exam_imgs["2026_q72_mammo"], core="Spiculated margin은 추적 관찰이 아니라 조직검사로 연결됩니다."
)
add_breast_exam(
    "2026 연계-73", "촉지되는 유방 종괴에서 MRI의 역할로 옳은 것은?<br>① 1차 선별검사<br>② 미세석회화 평가<br>③ 조직검사 대체<br>④ 암 진단 후 불필요<br>⑤ 수술 전 병변 범위와 다발성 평가",
    "⑤", "MRI는 수술 전 병변 범위, 다발성, 반대측 병변 평가에 유용합니다.",
    [("①", "일반 여성의 1차 선별검사는 유방촬영술입니다."), ("②", "미세석회화 평가는 mammography가 우수합니다."), ("③", "낮은 특이도로 조직검사를 대체하지 못합니다."), ("④", "수술 전 병기 결정에 필요할 수 있습니다."), ("⑤", "옳습니다.")],
    core="MRI는 가장 민감하지만 확진검사가 아니라 문제 해결과 범위 평가에 사용합니다."
)
add_breast_exam(
    "2023 연계-92", "유방 검사에 대한 설명 중 옳은 것은?<br>① 미세석회화는 초음파가 더 좋다.<br>② 조직 겹침을 극복한 기술은 elastogram이다.<br>③ 초음파는 조직검사를 유도하는 데 유용하다.<br>④ MRI는 민감도와 특이도가 모두 높다.<br>⑤ 보형물이 있으면 MRI가 유용하지 않다.",
    "③", "초음파는 병변을 실시간으로 보면서 조직검사와 중재시술을 유도할 수 있습니다.",
    [("①", "미세석회화는 mammography가 우수합니다."), ("②", "조직 겹침을 줄이는 기술은 DBT입니다."), ("③", "옳습니다."), ("④", "MRI는 민감도가 높고 특이도는 상대적으로 낮습니다."), ("⑤", "보형물 평가에는 MRI가 유용합니다.")],
    core="검사법의 장단점을 서로 대체 관계가 아니라 보완 관계로 구분합니다."
)
add_breast_exam(
    "2023 연계-94", "57세 무증상 여성의 CC/MLO 영상에서 화살표 병변이 보인다. 옳은 것은?<br>① Category 0<br>② 다음 검사로 MRI<br>③ 정밀검사를 위해 유방초음파<br>④ 6개월 후 유방촬영 추적<br>⑤ 오른쪽 내측 상방 병변",
    "③", "불규칙하고 침상 경계를 가진 악성 의심 종괴이므로 초음파로 확인하고 조직검사로 이어집니다.",
    [("①", "악성 의심 소견이 명확해 단순 Category 0이 아닙니다."), ("②", "우선 초음파와 조직검사가 필요합니다."), ("③", "옳습니다."), ("④", "Category 5 병변은 추적 대상이 아닙니다."), ("⑤", "족보 해설상 우측 하외측 사분면입니다.")],
    image=breast_exam_imgs["2023_q94_mammo"], core="악성 mammography 소견은 초음파와 조직검사로 연결합니다."
)
add_breast_exam(
    "2022 연계-94", "유방 검사에 대한 설명 중 옳은 것은?<br>① 치밀유방에서 미세석회화 진단에 mammography가 유용하지 않다.<br>② 조직 겹침을 극복한 기술은 elastogram이다.<br>③ 초음파는 조직검사를 유도하는 데 유용하다.<br>④ MRI는 민감도와 특이도가 모두 높다.<br>⑤ 보형물이 있으면 MRI가 유용하지 않다.",
    "③", "초음파는 조직검사를 실시간으로 유도하는 데 가장 편리한 검사입니다.",
    [("①", "치밀유방에서도 미세석회화는 mammography로 평가합니다."), ("②", "해당 기술은 DBT입니다."), ("③", "옳습니다."), ("④", "MRI의 특이도는 낮을 수 있습니다."), ("⑤", "보형물 환자에서 MRI가 유용합니다.")]
)
add_breast_exam(
    "2022 연계-95", "40–69세 무증상 여성에서 유방암 사망률 감소가 입증되어 2년마다 권고되는 검사는?<br>① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    "①", "국가검진에서 권고되는 검사는 유방촬영술입니다.",
    [("①", "옳습니다."), ("②", "일상적 선별검사로 단독 권고되지 않습니다."), ("③", "고위험군 선별이나 문제 해결에 사용합니다."), ("④", "기본 국가검진 검사로 제시된 답은 아닙니다."), ("⑤", "형태 평가를 보조하는 검사입니다.")],
    core="40–69세 무증상 여성: 유방촬영술 2년마다."
)
add_breast_exam(
    "2022 연계-96", "71세 여성의 유방촬영술에서 종괴가 보인다. 적절한 설명은?<br>① Fatty breast<br>② Category 3<br>③ MRI 정밀검사<br>④ 초음파와 조직검사<br>⑤ Mass와 architectural distortion",
    "④", "Mass와 microcalcification이 있는 악성 의심 병변이므로 초음파와 조직검사가 필요합니다.",
    [("①", "고령이지만 치밀유방 소견입니다."), ("②", "최소 Category 4에 해당합니다."), ("③", "확진을 위한 첫 단계는 초음파와 조직검사입니다."), ("④", "옳습니다."), ("⑤", "구조 왜곡보다 microcalcification이 제시되었습니다.")],
    image=breast_exam_imgs["2022_q96_mammo"]
)
add_breast_exam(
    "2022 연계-97", "20년 전 유방 확대수술을 받은 45세 여성의 촉지 종괴를 가장 정확히 평가할 검사는?<br>① 초음파<br>② 확대유방촬영술<br>③ DBT<br>④ MRI<br>⑤ Chest CT",
    "④", "보형물과 주변 유방조직 평가에는 MRI가 가장 유용합니다.",
    [("①", "보조적으로 사용할 수 있으나 이 문항의 최적 검사는 MRI입니다."), ("②", "보형물로 평가가 제한됩니다."), ("③", "보형물 자체와 주변 조직 평가의 최적 검사는 아닙니다."), ("④", "옳습니다."), ("⑤", "유방 병변의 정밀 평가 검사가 아닙니다.")],
    image=breast_exam_imgs["2022_q97_implant"]
)
add_breast_exam(
    "2021 연계-91", "유방 검사에 대한 설명 중 옳은 것은?<br>① Mammography는 치밀유방에 유용하다.<br>② 조직 겹침을 극복한 기술은 elastogram이다.<br>③ 초음파는 조직검사나 다른 검사의 위치 판단에 유용하다.<br>④ MRI는 민감도와 특이도가 모두 높다.",
    "③", "초음파는 병변의 실시간 위치 확인과 조직검사 유도에 유용합니다.",
    [("①", "치밀유방에서는 mammography 민감도가 감소합니다."), ("②", "조직 겹침을 줄이는 기술은 DBT입니다."), ("③", "옳습니다."), ("④", "MRI는 민감도가 높지만 특이도는 낮을 수 있습니다.")]
)
add_breast_exam(
    "2021 연계-92", "40–69세 무증상 여성에서 2년마다 시행할 것이 권고되는 유방암 검진 검사는?<br>① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    "①", "유방촬영술은 유방암 사망률 감소가 입증된 기본 선별검사입니다.",
    [("①", "옳습니다."), ("②", "일상적 선별검사로 단독 권고되지 않습니다."), ("③", "고위험군에 선택적으로 사용합니다."), ("④", "기본 권고 검사로 제시되지 않습니다."), ("⑤", "보조 검사입니다.")]
)
add_breast_exam(
    "2021 연계-93", "52세 무증상 여성의 mammography에서 irregular spiculated mass가 보인다. 옳은 것은?<br>① Category 3<br>② Microcalcification이 보인다.<br>③ 지방성 실질이다.<br>④ 초음파와 조직검사를 시행한다.<br>⑤ MRI로 확진한다.",
    "④", "Spiculated mass는 Category 4 이상 악성 의심 병변으로 초음파와 조직검사가 필요합니다.",
    [("①", "Probably benign이 아닙니다."), ("②", "족보 영상은 주로 spiculated mass를 제시했습니다."), ("③", "치밀한 실질입니다."), ("④", "옳습니다."), ("⑤", "MRI는 확진검사가 아닙니다.")],
    image=breast_exam_imgs["2021_q93_mammo"]
)
add_breast_exam(
    "2021 연계-94", "20년 전 유방 확대수술을 받은 여성의 촉지 종괴를 가장 정확히 평가할 검사는?<br>① 초음파<br>② 확대유방촬영술<br>③ DBT<br>④ MRI<br>⑤ Chest CT",
    "④", "보형물 삽입 환자에서 MRI는 보형물과 주변 조직을 함께 평가하는 데 유용합니다.",
    [("①", "보조적으로 사용할 수 있지만 이 문항의 최적 검사는 MRI입니다."), ("②", "보형물 때문에 평가가 제한됩니다."), ("③", "최적 검사가 아닙니다."), ("④", "옳습니다."), ("⑤", "유방 정밀검사로 적절하지 않습니다.")],
    image=breast_exam_imgs["2021_q94_implant"]
)
add_breast_exam(
    "2020 연계-95", "유방 검사에 대한 설명 중 옳은 것은?<br>① MRI는 민감도가 낮다.<br>② 조직 겹침에 따른 2D mammography의 한계를 줄이기 위해 DBT가 개발되었다.<br>③ Mammography는 치밀유방에 유용하다.<br>④ 탄성초음파는 탄성도를 이용하지 않는다.<br>⑤ 치밀유방에는 초음파를 사용하지 않는다.",
    "②", "DBT는 여러 각도의 영상을 재구성해 조직 겹침을 줄입니다.",
    [("①", "MRI는 민감도가 매우 높습니다."), ("②", "옳습니다."), ("③", "치밀유방에서는 민감도가 감소합니다."), ("④", "탄성초음파는 병변의 경도를 평가합니다."), ("⑤", "치밀유방의 촉지 종괴 평가에 초음파가 유용합니다.")]
)
add_breast_exam(
    "2020 연계-96", "40–69세 무증상 여성에서 2년마다 권고되는 유방암 검진 검사는?<br>① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    "①", "유방촬영술이 유방암 사망률 감소를 입증한 기본 선별검사입니다.",
    [("①", "옳습니다."), ("②", "일상적 선별검사로 단독 권고되지 않습니다."), ("③", "고위험군에서 선택적으로 사용합니다."), ("④", "기본 권고 검사로 제시되지 않습니다."), ("⑤", "보조 검사입니다.")]
)
add_breast_exam(
    "2019 연계-61 [복원]", "유선조직 겹침으로 mammography의 민감도와 특이도가 낮아지는 한계를 줄이기 위해 개발된 기술은?",
    "③ Digital breast tomosynthesis", "DBT는 여러 각도의 투영 영상을 단층으로 재구성해 정상 조직의 겹침을 줄입니다.",
    [("①", "치밀유방에서는 mammography 민감도가 감소합니다."), ("③", "족보 정답입니다."), ("④", "탄성초음파는 경도를 평가하는 별도의 보조 검사입니다."), ("⑤", "MRI는 민감도가 낮은 검사가 아닙니다.")],
    core="원문 보기 일부가 불완전하게 복원되었으나 족보 정답은 DBT입니다."
)
add_breast_exam(
    "2019 연계-62", "40–69세 무증상 여성에서 2년마다 시행하도록 권고되는 유방암 검진 검사는?<br>① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    "①", "유방촬영술은 유방암 사망률을 유의하게 감소시킨다고 입증된 검진 검사입니다.",
    [("①", "옳습니다."), ("②", "일상적 검진으로 단독 권고되지 않습니다."), ("③", "고위험군에 사용합니다."), ("④", "기본 국가검진 답은 아닙니다."), ("⑤", "보조 검사입니다.")]
)
add_breast_exam(
    "2019 연계-63 [복원]", "유방촬영술에서 큰 종괴가 보인다. 복원된 족보에서 옳은 설명은?<br>① Irregular spiculated mass이지만 Category 3이다.<br>② MRI로 최종 진단한다.<br>③ Mass와 microcalcification이 보인다.<br>④ 6개월 후 추적한다.<br>⑤ 지방성 실질이다.",
    "③", "족보 정답은 mass와 microcalcification이 관찰된다는 설명입니다. 다만 원본 영상과 일부 보기는 완전하게 복원되지 않았습니다.",
    [("①", "Spiculated mass는 Category 3이 아닙니다."), ("②", "MRI는 확진검사가 아닙니다."), ("③", "족보에 제시된 정답입니다."), ("④", "악성 의심 소견은 단기 추적 대상이 아닙니다."), ("⑤", "족보 해설은 fatty breast가 아니라고 정리합니다.")],
    image=breast_exam_imgs["2019_q63_mammo"], core="복원 문항의 불확실성은 유지하되, 족보 정답과 악성 소견의 처치를 구분합니다."
)
add_breast_exam(
    "2019 연계-64", "비촉지성 유방 병변의 수술 전 위치를 표시하기 위해 시행한 시술의 명칭은?<br>① 초음파 유도하 침 위치 결정술<br>② 유방촬영술 유도하 침 위치 결정술<br>③ 입체정위 조직검사<br>④ Core needle biopsy<br>⑤ Vacuum-assisted biopsy",
    "①", "초음파에서 보이는 비촉지성 병변에 hook wire를 삽입해 수술 위치를 표시한 시술입니다.",
    [("①", "옳습니다."), ("②", "초음파에서 보이지 않고 mammography에서만 보이는 미세석회화에 사용할 수 있습니다."), ("③", "조직을 채취하는 검사입니다."), ("④", "조직을 채취하는 검사입니다."), ("⑤", "진공으로 조직을 연속 채취하는 검사입니다.")],
    image=breast_exam_imgs["2019_q64_wire"], core="영상에서 보이는 방법으로 병변 위치를 표시합니다."
)
'''
source = source.replace("\n# ---------- Export ----------", breast_school_code + "\n# ---------- Export ----------", 1)

# Export both required Breast Imaging subdecks and use new, distinct filenames.
source = source.replace(
    '[breast_jbl],\n    "외과학 입문__3. 계통별 수술__유방영상학 1, 2 (최혜영) by 이용화 0826.apkg"',
    '[breast_jbl, breast_school],\n    "외과학 입문__3. 계통별 수술__유방영상학 1, 2 (최혜영) by 이용화 0826_최종검수.apkg"',
)
source = source.replace(
    '"외과학 입문__3. 계통별 수술__소아외과 (소화기학) (박태진) by 이용화 0826_개선판.apkg"',
    '"외과학 입문__3. 계통별 수술__소아외과 (소화기학) (박태진) by 이용화 0826_최종검수.apkg"',
)
source = source.replace(
    '  - 1. JBL: {len(breast_jbl.notes)} notes\n',
    '  - 1. JBL: {len(breast_jbl.notes)} notes\n  - 2. 족보: {len(breast_school.notes)} notes\n',
)

# -----------------------------------------------------------------------------
# Post-build APKG verification: deck trees, counts, note types, tags and media
# -----------------------------------------------------------------------------
validation_code = r'''

# ---------- Final package validation ----------
def _collection_db(apkg_path: Path) -> Path:
    with zipfile.ZipFile(apkg_path) as zf:
        candidates = [n for n in zf.namelist() if n in {"collection.anki2", "collection.anki21", "collection.anki21b"}]
        if not candidates:
            raise AssertionError(f"No Anki collection DB in {apkg_path.name}")
        name = candidates[0]
        data = zf.read(name)
        if name.endswith(".anki21b"):
            try:
                data = zstd.ZstdDecompressor().decompress(data)
            except zstd.ZstdError:
                with zstd.ZstdDecompressor().stream_reader(data) as reader:
                    data = reader.read()
    temp = Path(tempfile.mkstemp(suffix=".sqlite")[1])
    temp.write_bytes(data)
    return temp


def validate_apkg(apkg_path: Path, expected: dict[str, int | None]) -> dict[str, int]:
    db_path = _collection_db(apkg_path)
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        decks_raw, models_raw = cur.execute("SELECT decks, models FROM col LIMIT 1").fetchone()
        if isinstance(decks_raw, bytes):
            decks_raw = decks_raw.decode("utf-8")
        if isinstance(models_raw, bytes):
            models_raw = models_raw.decode("utf-8")
        decks = json.loads(decks_raw)
        models = json.loads(models_raw)
        did_to_name = {int(did): obj["name"] for did, obj in decks.items()}
        card_counts: dict[str, int] = {}
        for did, count in cur.execute("SELECT did, COUNT(*) FROM cards GROUP BY did"):
            card_counts[did_to_name.get(int(did), f"did:{did}")] = int(count)

        for deck_name, exact_count in expected.items():
            if deck_name not in card_counts:
                raise AssertionError(f"Missing subdeck: {deck_name}; found={sorted(card_counts)}")
            if card_counts[deck_name] <= 0:
                raise AssertionError(f"Empty subdeck: {deck_name}")
            if exact_count is not None and card_counts[deck_name] != exact_count:
                raise AssertionError(f"Unexpected card count for {deck_name}: {card_counts[deck_name]} != {exact_count}")

        model_names = {m["name"] for m in models.values()}
        required_models = {"!표준화 cloze ver2.1", "!표준화 Basic ver2.1", "!표준화 뉴족보 ver2.1"}
        missing_models = required_models - model_names
        if missing_models:
            raise AssertionError(f"Missing standardized note types: {sorted(missing_models)}; found={sorted(model_names)}")

        note_rows = cur.execute("SELECT flds, tags FROM notes").fetchall()
        if any((tags or "").strip() for _, tags in note_rows):
            raise AssertionError("Tags were found although the deck must be tag-free")
        all_text = "\n".join((flds or "").replace("\x1f", "\n") for flds, _ in note_rows)
        banned = ["왕족", "가져갈 한 줄", "꼭 기억", "헷갈리지", "아래는", "이 카드", "강의에서는", "교수님이"]
        hits = [phrase for phrase in banned if phrase in all_text]
        if hits:
            raise AssertionError(f"Creator/editor voice remains: {hits}")
        image_refs = set(re.findall(r'<img[^>]+src=["\']([^"\']+)', all_text))
        con.close()

        with zipfile.ZipFile(apkg_path) as zf:
            media_map = json.loads(zf.read("media").decode("utf-8")) if "media" in zf.namelist() else {}
            packaged_names = set(media_map.values())
            missing_media = image_refs - packaged_names
            if missing_media:
                raise AssertionError(f"Missing referenced media in {apkg_path.name}: {sorted(missing_media)}")
        return card_counts
    finally:
        db_path.unlink(missing_ok=True)


peds_expected = {
    peds_root + "::1. JBL": None,
    peds_root + "::2. 참공": 5,
    peds_root + "::3. 족보": 6,
    peds_root + "::4. KMLE": 12,
}
breast_expected = {
    breast_root + "::1. JBL": None,
    breast_root + "::2. 족보": 20,
}
peds_counts = validate_apkg(peds_out, peds_expected)
breast_counts = validate_apkg(breast_out, breast_expected)

validation_report = OUT / "FINAL_VALIDATION.txt"
validation_report.write_text(
    "FINAL VALIDATION: PASS\n\n"
    + "Pediatric Surgery\n"
    + "\n".join(f"- {name}: {count} cards" for name, count in sorted(peds_counts.items()) if name.startswith(peds_root))
    + "\n\nBreast Imaging\n"
    + "\n".join(f"- {name}: {count} cards" for name, count in sorted(breast_counts.items()) if name.startswith(breast_root))
    + "\n\n- Standardized note types: PASS\n- Empty/missing subdecks: NONE\n- Tags: NONE\n- Missing referenced media: NONE\n- Creator/editor voice scan: PASS\n",
    encoding="utf-8",
)

final_zip = OUT / "소아외과_유방영상학_APKG_최종검수.zip"
with zipfile.ZipFile(final_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.write(peds_out, peds_out.name)
    zf.write(breast_out, breast_out.name)
    zf.write(validation_report, validation_report.name)
print(validation_report.read_text(encoding="utf-8"))
print(f"FINAL_ZIP={final_zip} ({final_zip.stat().st_size:,} bytes)")
'''
source += validation_code

namespace = {"__file__": str(base_script), "__name__": "__main__"}
exec(compile(source, str(base_script), "exec"), namespace)
