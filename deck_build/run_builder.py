from pathlib import Path
import json
import re
import sqlite3
import tempfile
import zipfile

import genanki
import gdown
import zstandard as zstd

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

# Public build copies of the bounded source set.
source = source.replace("1tpNLSvDcJUx0McmWiLpt8xTePeVJd1OB", "1fHakVRBpkVmjhr3RvA3QEHwRV7XuOs6o")
source = source.replace("1lbWoXqb_tleGdSRP0QIisHpXde4uFdkk", "1RF9-QVVH4VZUrJuGfKwtVJrkGA2VqBR8")
# Shared standardized note-type sources.
source = source.replace("1BLh4HkPnUEpwVa-7AaZYhKrttNa2p363", "1Kz_cvHYU3LPDx5VvwGRk0bnzuWHwsGmO")
source = source.replace("1fIC9_LN1Vac5qBMhdF9DB6WYLopAqxJv", "1Xa8q6_XXXtzdGbDSOwmyh31dKzFOv0Hh")
source = source.replace("1iX31-Lv52dFqYvpOXTr5MkKmj2UbdvwW", "1Kz_cvHYU3LPDx5VvwGRk0bnzuWHwsGmO")

# The Breast Imaging image questions reuse lecture cases. The corresponding
# lecture crops are placed both in JBL and in the school-exam cards.
source = re.sub(
    r'^EXAM_PDF = download_drive\([^\n]+\)$',
    'EXAM_PDF = BREAST_PDF',
    source,
    flags=re.MULTILINE,
)
replacement = '''# Image-bearing Breast Imaging questions from 2019-2026.
# Each question is linked to the corresponding lecture case image.
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
    raise RuntimeError(f"Could not replace Breast Imaging media block; matches={count}")

# The standardized exam note type uses Korean field names. Map them explicitly
# so the school-exam and KMLE notes create real cards rather than empty notes.
field_override = r'''
def fields_for_model(model: genanki.Model, front: str, back: str, *, text: str | None = None, extra: str | None = None) -> list[str]:
    names = model_field_names(model)
    title_match = re.match(r"\s*<b>(.*?)</b>(?:<br>\s*){1,2}(.*)", front, flags=re.DOTALL)
    problem_no = title_match.group(1).strip() if title_match else ""
    body = title_match.group(2).strip() if title_match else front
    values: list[str] = []
    for name in names:
        key = name.lower().replace("_", " ").strip()
        if "back extra" in key or key in {"extra", "remarks", "remark", "해설", "설명"}:
            values.append(extra if extra is not None else back)
        elif key == "text" or "cloze" in key:
            values.append(text if text is not None else front)
        elif key == "문제번호":
            values.append(problem_no)
        elif key in {"본문", "문제 본문"}:
            values.append(body)
        elif key in {"정답 및 해설", "정답/해설"}:
            values.append(back)
        elif "front" in key or key in {"question", "문제"}:
            values.append(front)
        elif "back" in key or key in {"answer", "정답"}:
            values.append(back)
        else:
            values.append("")
    return values

'''
source = source.replace("\ndef img_html(filename: str, alt: str = \"\") -> str:\n", "\n" + field_override + "def img_html(filename: str, alt: str = \"\") -> str:\n", 1)

# Neutral, textbook-like wording. Source labels are retained only where they
# identify a question year or image set.
wording_replacements = {
    "<div class='warn'><b>가져갈 한 줄</b>": "<div class='warn'><b>핵심 정리</b>",
    "KMLE의 복벽갈림증 문제도 질환명보다 노출된 장에서 생기는 열·수분 손실에 대한 초기 대응을 묻습니다.": "노출된 장은 열과 수분 손실을 크게 증가시키므로 초기 보온과 수액 공급이 필요합니다.",
    "아래는 같은 단서를 반복해서 물은 실제 KMLE 영상들입니다.": "관련 KMLE 영상에서도 정중 위치와 혀 움직임이 반복적으로 제시됩니다.",
    "강의에서는 세부 술기보다 병력에서 이 단서를 먼저 잡는 수준을 강조했습니다. 학교 족보에서 같은 단서가 실제 영상과 함께 반복되었습니다.": "병력의 세 단서가 진단의 출발점이며, 관련 학교 문제에서도 같은 단서가 영상과 함께 제시됩니다.",
    "아래는 실제로 출제된 모든 mammography 이미지 문제입니다. 연도는 달라도 '악성 소견 → 초음파 → 조직검사'라는 판단을 반복합니다.": "2019–2026 mammography 영상 문제들이다. 악성 소견이 보이면 초음파로 병변을 평가하고 조직검사로 확진한다.",
    "2026 Q71은 강의 마지막 증례와 같은 악성 고형 종괴를 보여주고 Category 4C + 초음파 유도 core biopsy를 답으로 요구했습니다.": "2026 Q71에서는 악성 고형 종괴를 BI-RADS 4C로 평가하고 초음파 유도 중심침생검을 선택한다.",
    "2019~2020 족보에서 직접 반복되었습니다.": "2019–2020 문제에서 반복되었다.",
    "2026 Q73의 정답도 수술 전 범위와 다발성 평가였습니다.": "2026 Q73에서는 수술 전 병변 범위와 다발성 평가가 정답이다.",
    "2019 Q64는 강의 사진 그대로 시술명을 물었습니다.": "2019 Q64에서는 이 영상으로 시술명을 물었다.",
    "2021과 2022에 같은 강의 이미지가 반복 출제되었습니다. 이 족보의 핵심은 보형물이 있는 환자에서 MRI가 유용하다는 것입니다.": "2021·2022 문제에서 같은 유형이 반복되었다. 보형물이 있는 환자의 평가에는 MRI가 유용하다.",
    "강의 마지막 증례의 흐름입니다. Mammography → US/BI-RADS 4C → core biopsy → 암 확진 → MRI extent evaluation을 하나의 판단 사슬로 익힙니다.": "촉지 종괴는 mammography 후 초음파와 BI-RADS 평가를 거쳐 중심침생검으로 확진하고, 암이 확인되면 MRI로 범위를 평가한다.",
    "같은 왕족 단서의 반복입니다.": "정중 위치와 혀 움직임은 갑상설관낭종의 전형적 소견입니다.",
    "강의 직접 핵심은 혈성 점액변으로 장중첩증을 알아보는 것입니다.": "혈성 점액변과 주기적 복통은 장중첩증을 시사합니다.",
    "담도폐쇄증 치료는 강의 범위 밖이고, 이 문제는 red flag 적용용입니다.": "담도폐쇄증의 세부 치료보다 황달과 회색 변을 경고 소견으로 인식하는 것이 중요합니다.",
    "이번 강의의 직접 범위는 아닙니다.": "세부 치료는 이 자료의 직접 범위에 포함되지 않습니다.",
    "강의에서는 질환의 세부 치료보다 이 두 단서를 먼저 알아보는 수준이 핵심입니다.": "혈성 점액변과 담즙성 구토가 각각 장중첩증과 중장염전을 시사합니다.",
    "기억할 경계는 2%와 95%입니다.": "처치가 달라지는 경계값은 2%와 95%입니다.",
}
for old, new in wording_replacements.items():
    source = source.replace(old, new)

# Add a dedicated Breast Imaging school-exam subdeck.
source = source.replace(
    'breast_jbl = genanki.Deck(deterministic_id(breast_root+"::1. JBL"), breast_root+"::1. JBL")\n',
    'breast_jbl = genanki.Deck(deterministic_id(breast_root+"::1. JBL"), breast_root+"::1. JBL")\n'
    'breast_school = genanki.Deck(deterministic_id(breast_root+"::2. 족보"), breast_root+"::2. 족보")\n',
    1,
)

breast_exam_block = r'''
# ---------- Breast Imaging school examinations ----------
def breast_options(lines: list[str]) -> str:
    return "<br>".join(lines)

add_exam(
    breast_school,
    "<b>2026 연계-70</b><br><br>다음의 유방 영상 진단 기법에 대한 설명 중 옳은 것은?<br>"
    "① 유방은 연부조직으로 구성되므로 높은 에너지 X-ray가 유리하다.<br>"
    "② 유방초음파는 낭성과 고형 종괴를 감별하고, 치밀유방에서 보이지 않지만 만져지는 종괴 평가에 유용하다.<br>"
    "③ 유방 MRI는 특이도가 가장 높아 조직검사를 대체한다.<br>"
    "④ 유방 MRI는 미세석회화 평가에 가장 유용하다.<br>"
    "⑤ 조직검사에서 암이 진단되면 MRI는 필요하지 않다.",
    exam_back(
        "②",
        "유방촬영술은 저에너지 X-ray를 사용하며 미세석회화 평가에 가장 유용하다. 초음파는 낭성·고형 감별과 치밀유방의 촉지 종괴 평가에 유용하다. MRI는 민감도가 높지만 특이도가 낮아 조직검사를 대체하지 못하며, 수술 전 범위 평가에 사용된다.",
        takeaway="검사별 역할: mammography는 미세석회화, 초음파는 낭성·고형 감별과 시술 유도, MRI는 범위 평가.",
    ),
)
add_exam(
    breast_school,
    "<b>2026 연계-71</b><br><br>우측 유방의 촉지 종괴에 대한 초음파 영상이다. 가장 적절한 BI-RADS 범주와 권고의 조합은?<br>"
    "① Category 3 – 6개월 추적 초음파<br>② Category 4A – 단기 추적 관찰<br>③ Category 4B – 유방 MRI<br>④ Category 4C – 초음파 유도하 중심침생검<br>⑤ Category 6 – 치료 없이 추적 관찰"
    + img_html(breast_exam_imgs["2026_q71_us"], "2026 초음파 문제"),
    exam_back(
        "④",
        "불규칙한 고형 종괴와 비양성 경계는 악성을 의심하게 한다. BI-RADS 4 병변은 조직검사가 필요하며, 영상 소견이 매우 의심스러운 경우 4C로 평가할 수 있다.",
        takeaway="BI-RADS 4–5는 추적이 아니라 조직검사로 연결된다.",
    ),
)
add_exam(
    breast_school,
    "<b>2026 연계-72</b><br><br>촉지 종괴가 있는 43세 여성의 유방촬영술이다. 옳은 설명은?<br>"
    "① 유방초음파 후 조직검사를 시행한다.<br>② 병변은 BI-RADS Category 3이다.<br>③ 6개월 후 유방촬영술로 추적한다.<br>④ 유방 실질은 유형 A이다.<br>⑤ MRI를 시행하면 조직검사를 생략할 수 있다."
    + img_html(breast_exam_imgs["2026_q72_mammo"], "2026 mammography 문제"),
    exam_back(
        "①",
        "Spiculated margin을 보이는 종괴는 BI-RADS 4 또는 5에 해당한다. 초음파로 병변을 정밀 평가하고 조직검사로 확진한다. MRI는 조직검사를 대체하지 못한다.",
        takeaway="Spiculated mass는 단기 추적 대상이 아니다.",
    ),
)
add_exam(
    breast_school,
    "<b>2026 연계-73</b><br><br>유방에 멍울이 촉지되는 환자에서 MRI의 역할에 대한 설명으로 옳은 것은?<br>"
    "① 일차 선별검사로 사용한다.<br>② 미세석회화 평가에 가장 유용하다.<br>③ 특이도가 가장 높아 조직검사를 대체한다.<br>④ 조직검사에서 암이 진단되면 필요하지 않다.<br>⑤ 수술 전 병변의 범위와 다발성 병변 평가에 중요하다.",
    exam_back(
        "⑤",
        "MRI는 민감도가 높아 수술 전 병변 범위, 다발성 및 반대측 병변 평가에 유용하다. 특이도가 낮으므로 확진을 위한 조직검사를 대체하지 못한다.",
        takeaway="암 확진 뒤 MRI는 범위를 정하는 검사다.",
    ),
)
add_exam(
    breast_school,
    "<b>2023 연계-92</b><br><br>유방 검사에 대한 설명 중 옳은 것은?<br>"
    "① 미세석회화는 초음파가 더 잘 본다.<br>② 조직 겹침을 줄이기 위해 elastography가 개발되었다.<br>③ 초음파는 유방 조직검사를 유도하는 데 유용하다.<br>④ MRI는 민감도와 특이도가 모두 높아 확진검사로 사용한다.<br>⑤ 보형물 환자에서 MRI는 유용하지 않다.",
    exam_back(
        "③",
        "미세석회화는 mammography가 가장 잘 평가한다. 조직 겹침을 줄이는 기술은 DBT이다. MRI는 민감도가 높지만 특이도가 낮고, 보형물 평가에도 유용하다.",
        takeaway="초음파는 실시간으로 바늘 위치를 확인할 수 있어 조직검사 유도에 적합하다.",
    ),
)
add_exam(
    breast_school,
    "<b>2023 연계-94</b><br><br>57세 무증상 여성의 CC·MLO 유방촬영술이다. 다음 단계로 적절한 것은?<br>"
    "① Category 0으로 판정한다.<br>② MRI를 시행한다.<br>③ 정밀검사를 위해 유방초음파를 시행한다.<br>④ 6개월 뒤 유방촬영술로 추적한다.<br>⑤ 병변은 우측 내상방에 있다."
    + img_html(breast_exam_imgs["2023_q94_mammo"], "2023 mammography 문제"),
    exam_back(
        "③",
        "불규칙하고 침상 경계를 보이는 종괴는 Category 5에 해당하며 조직검사가 필요하다. 치밀유방의 종괴는 초음파로 추가 평가한다. 병변은 우측 하외측에 위치한다.",
        takeaway="악성 종괴가 보이면 초음파와 조직검사로 이어진다.",
    ),
)
add_exam(
    breast_school,
    "<b>2022 연계-94</b><br><br>유방 검사에 대한 설명 중 옳은 것은?<br>"
    "① 치밀유방에서 유방촬영술은 미세석회화 진단에 유용하지 않다.<br>② 조직 겹침을 줄이는 기술은 elastography이다.<br>③ 초음파는 유방 조직검사를 유도하는 데 유용하다.<br>④ MRI는 민감도와 특이도가 모두 높다.<br>⑤ 보형물 환자에서 MRI는 유용하지 않다.",
    exam_back(
        "③",
        "치밀유방에서도 미세석회화는 mammography로 평가한다. DBT는 조직 겹침을 줄이고, MRI는 민감도가 높지만 특이도가 낮다.",
        takeaway="초음파는 병변 확인뿐 아니라 시술 유도에 사용된다.",
    ),
)
add_exam(
    breast_school,
    "<b>2022 연계-95</b><br><br>40–69세 무증상 여성에서 유방암 검진을 위해 2년마다 권고되는 영상검사는?<br>"
    "① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    exam_back(
        "①",
        "무증상 여성의 국가검진 기본 검사는 유방촬영술이다. 초음파는 일상적 단독 선별검사로 권고되지 않는다.",
        takeaway="40–69세 무증상 여성: mammography 2년마다.",
    ),
)
add_exam(
    breast_school,
    "<b>2022 연계-96</b><br><br>71세 여성의 촉지 종괴에 대한 유방촬영술이다. 옳은 설명은?<br>"
    "① Fatty breast이다.<br>② BI-RADS Category 3이다.<br>③ MRI 정밀검사가 우선이다.<br>④ 초음파와 조직검사를 후속으로 시행한다.<br>⑤ Mass와 architectural distortion이 보인다."
    + img_html(breast_exam_imgs["2022_q96_mammo"], "2022 mammography 문제"),
    exam_back(
        "④",
        "치밀유방에서 종괴와 미세석회화가 보이며 악성이 의심된다. 초음파로 병변을 평가하고 조직검사로 확진한다. 구조왜곡과 미세석회화를 구분해야 한다.",
        takeaway="의심스러운 mass와 calcification은 Category 4 이상으로 보고 조직검사한다.",
    ),
)
add_exam(
    breast_school,
    "<b>2022 연계-97</b><br><br>20년 전 유방 확대수술을 받은 45세 여성의 촉지 종괴를 평가할 가장 적절한 검사는?<br>"
    "① 초음파<br>② 확대 유방촬영술<br>③ DBT<br>④ MRI<br>⑤ 흉부 CT"
    + img_html(breast_exam_imgs["2022_q97_implant"], "2022 보형물 문제"),
    exam_back(
        "④",
        "MRI는 보형물의 상태와 보형물 주변 유방조직을 평가하는 데 유용하다.",
        takeaway="유방 보형물 환자의 문제 해결 검사로 MRI를 고려한다.",
    ),
)
add_exam(
    breast_school,
    "<b>2021 연계-91</b><br><br>유방 검사에 대한 설명 중 옳은 것은?<br>"
    "① 유방촬영술은 치밀유방에서 유용하다.<br>② 조직 겹침을 줄이기 위해 elastography가 개발되었다.<br>③ 초음파는 조직검사나 다른 검사의 위치 판단에 유용하다.<br>④ MRI는 민감도와 특이도가 모두 높다.",
    exam_back(
        "③",
        "초음파는 실시간 위치 확인과 조직검사 유도에 유용하다. DBT는 조직 겹침을 줄이고, MRI는 높은 민감도에 비해 특이도가 낮다.",
        takeaway="초음파의 중요한 역할 중 하나는 시술 유도다.",
    ),
)
add_exam(
    breast_school,
    "<b>2021 연계-92</b><br><br>40–69세 무증상 여성에서 유방암 검진을 위해 2년마다 권고되는 영상검사는?<br>"
    "① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    exam_back("①", "유방촬영술은 유방암 사망률 감소가 입증된 기본 선별검사다.", takeaway="40–69세 무증상 여성: mammography 2년마다."),
)
add_exam(
    breast_school,
    "<b>2021 연계-93</b><br><br>무증상 52세 여성의 유방촬영술이다. 옳은 설명은?<br>"
    "① Irregular spiculated mass이므로 Category 3이다.<br>② Microcalcification이 보인다.<br>③ 지방성 유방이다.<br>④ 초음파와 조직검사를 시행한다.<br>⑤ MRI로 확진한다."
    + img_html(breast_exam_imgs["2021_q93_mammo"], "2021 mammography 문제"),
    exam_back(
        "④",
        "Irregular spiculated mass는 Category 4 이상으로 평가하며, 초음파 후 조직검사가 필요하다. MRI는 확진검사가 아니다.",
        takeaway="침상 경계는 강한 악성 소견이다.",
    ),
)
add_exam(
    breast_school,
    "<b>2021 연계-94</b><br><br>20년 전 유방 확대수술을 받은 45세 여성의 촉지 종괴를 평가할 가장 적절한 검사는?<br>"
    "① 초음파<br>② 확대 유방촬영술<br>③ DBT<br>④ MRI<br>⑤ 흉부 CT"
    + img_html(breast_exam_imgs["2021_q94_implant"], "2021 보형물 문제"),
    exam_back("④", "MRI는 보형물과 주변 유방조직 평가에 유용하다.", takeaway="보형물 관련 문제 해결에는 MRI를 고려한다."),
)
add_exam(
    breast_school,
    "<b>2020 연계-95</b><br><br>유방 영상기법에 대한 설명 중 옳은 것은?<br>"
    "① MRI는 민감도가 낮다.<br>② 유선조직 겹침으로 민감도와 특이도가 떨어지는 단점을 줄이기 위해 DBT가 개발되었다.<br>③ 유방촬영술은 치밀유방에 특히 유용하다.<br>④ 탄성초음파는 탄성도를 이용하지 않는다.<br>⑤ 치밀유방에는 초음파를 사용하지 않는다.",
    exam_back(
        "②",
        "DBT는 여러 각도의 영상을 재구성해 2D mammography의 조직 겹침을 줄인다. MRI는 민감도가 높고, 탄성초음파는 병변의 경도를 보조적으로 평가한다.",
        takeaway="DBT의 목적은 조직 중첩 감소다.",
    ),
)
add_exam(
    breast_school,
    "<b>2020 연계-96</b><br><br>40–69세 무증상 여성에서 유방암 검진을 위해 2년마다 권고되는 영상검사는?<br>"
    "① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    exam_back("①", "유방촬영술은 유방암 사망률 감소가 입증된 기본 선별검사다.", takeaway="40–69세 무증상 여성: mammography 2년마다."),
)
add_exam(
    breast_school,
    "<b>2019 연계-61</b><br><br>유방촬영 영상기법에 대한 설명 중 옳은 것은?<br>"
    "① 유방촬영술은 치밀유방에서 종괴 검출에 특히 유리하다.<br>③ 유선조직 겹침에 따른 민감도·특이도 저하를 줄이기 위해 DBT가 개발되었다.<br>⑤ 유방 MRI는 민감도가 낮다.",
    exam_back(
        "③",
        "DBT는 조직 겹침을 줄이기 위해 개발되었다. 치밀유방에서는 mammography의 종괴 검출 민감도가 떨어져 초음파가 보조적으로 사용되며, MRI의 민감도는 높다.",
        takeaway="검사별 장단점을 비교하는 반복 유형이다.",
    ),
)
add_exam(
    breast_school,
    "<b>2019 연계-62</b><br><br>40–69세 무증상 여성에서 유방암 검진을 위해 2년마다 권고되는 영상검사는?<br>"
    "① 유방촬영술<br>② 유방초음파<br>③ 유방 MRI<br>④ DBT<br>⑤ 탄성초음파",
    exam_back("①", "유방촬영술은 유방암 사망률 감소가 입증된 기본 선별검사다.", takeaway="40–69세 무증상 여성: mammography 2년마다."),
)
add_exam(
    breast_school,
    "<b>2019 연계-63 · 복원 제한</b><br><br>유방촬영술에서 큰 종괴가 화살표로 제시되었다. 복원된 선택지 중 옳은 것은?<br>"
    "① Spiculated irregular mass이므로 Category 3이다.<br>② MRI로 최종 확진한다.<br>③ 미세석회화와 mass가 있다.<br>④ 6개월 뒤 추적한다.<br>⑤ 지방성 유방이다."
    + img_html(breast_exam_imgs["2019_q63_mammo"], "2019 mammography 복원 문제"),
    exam_back(
        "복원상 ③",
        "원문 영상과 일부 선택지가 완전하게 남아 있지 않다. 기록상 정답은 ③으로 복원되었다. 다만 spiculated mass 자체는 Category 4–5 소견이며 MRI는 조직검사를 대체하지 않는다.",
        takeaway="불완전 복원 문제는 정답보다 영상 소견과 다음 처치를 우선 정리한다.",
    ),
)
add_exam(
    breast_school,
    "<b>2019 연계-64</b><br><br>비촉지성 유방 병변의 수술 전 위치를 표시하기 위해 초음파로 병변에 갈고리 철심을 삽입한 시술의 명칭은?<br>"
    "① 초음파 유도하 침 위치 결정술<br>② 유방촬영술 유도하 침 위치 결정술<br>③ 입체정위 조직검사<br>④ 중심침생검<br>⑤ 진공보조유방생검"
    + img_html(breast_exam_imgs["2019_q64_wire"], "2019 wire localization 문제"),
    exam_back(
        "①",
        "초음파에서 보이는 비촉지성 병변에 hook wire를 삽입해 수술 범위를 표시하는 시술이다. 초음파에서 보이지 않는 미세석회화는 mammography 유도로 위치를 표시할 수 있다.",
        takeaway="병변이 보이는 영상기법으로 wire localization을 유도한다.",
    ),
)

'''
source = source.replace("\n\n# ---------- Export ----------\n", "\n\n" + breast_exam_block + "# ---------- Export ----------\n", 1)

# Export both visible subdeck trees.
source = source.replace(
    '[breast_jbl],\n    "외과학 입문__3. 계통별 수술__유방영상학 1, 2 (최혜영) by 이용화 0826.apkg",',
    '[breast_jbl, breast_school],\n    "외과학 입문__3. 계통별 수술__유방영상학 1, 2 (최혜영) by 이용화 0826_최종개선판.apkg",',
    1,
)
source = source.replace(
    '"외과학 입문__3. 계통별 수술__소아외과 (소화기학) (박태진) by 이용화 0826_개선판.apkg",',
    '"외과학 입문__3. 계통별 수술__소아외과 (소화기학) (박태진) by 이용화 0826_최종개선판.apkg",',
    1,
)
source = source.replace(
    '  - 1. JBL: {len(breast_jbl.notes)} notes\n',
    '  - 1. JBL: {len(breast_jbl.notes)} notes\n  - 2. 족보: {len(breast_school.notes)} notes\n',
    1,
)

namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(source, str(script), "exec"), namespace)


def _collection_bytes(apkg: Path) -> bytes:
    with zipfile.ZipFile(apkg) as zf:
        for name in ("collection.anki2", "collection.anki21", "collection.anki21b"):
            if name in zf.namelist():
                data = zf.read(name)
                if name.endswith(".anki21b"):
                    try:
                        return zstd.ZstdDecompressor().decompress(data)
                    except zstd.ZstdError:
                        with zstd.ZstdDecompressor().stream_reader(data) as reader:
                            return reader.read()
                return data
    raise RuntimeError(f"No Anki collection database in {apkg}")


def validate_apkg(apkg: Path, required_suffixes: list[str]) -> dict[str, int]:
    data = _collection_bytes(apkg)
    tmp = Path(tempfile.mkstemp(suffix=".sqlite")[1])
    tmp.write_bytes(data)
    try:
        con = sqlite3.connect(str(tmp))
        cur = con.cursor()
        row = cur.execute("SELECT decks, models FROM col LIMIT 1").fetchone()
        decks = json.loads(row[0])
        models = json.loads(row[1])
        names = {int(did): cfg["name"] for did, cfg in decks.items()}
        counts = {int(did): int(n) for did, n in cur.execute("SELECT did, COUNT(*) FROM cards GROUP BY did")}
        by_name = {name: counts.get(did, 0) for did, name in names.items()}
        for suffix in required_suffixes:
            matches = [(name, n) for name, n in by_name.items() if name.endswith(suffix)]
            if len(matches) != 1:
                raise AssertionError(f"{apkg.name}: required deck {suffix!r} not found exactly once: {matches}")
            if matches[0][1] <= 0:
                raise AssertionError(f"{apkg.name}: deck {matches[0][0]} has no generated cards")
        nonempty_tags = cur.execute("SELECT COUNT(*) FROM notes WHERE TRIM(tags) <> ''").fetchone()[0]
        if nonempty_tags:
            raise AssertionError(f"{apkg.name}: {nonempty_tags} notes contain tags")
        model_names = {cfg.get("name", "") for cfg in models.values()}
        required_models = {"!표준화 cloze ver2.1", "!표준화 Basic ver2.1", "!표준화 뉴족보 ver2.1"}
        if not required_models.issubset(model_names):
            raise AssertionError(f"{apkg.name}: standardized models missing: {required_models - model_names}")
        con.close()
        return {name: n for name, n in sorted(by_name.items()) if n > 0}
    finally:
        tmp.unlink(missing_ok=True)

peds_out = Path(namespace["peds_out"])
breast_out = Path(namespace["breast_out"])
peds_validation = validate_apkg(peds_out, ["::1. JBL", "::2. 참공", "::3. 족보", "::4. KMLE"])
breast_validation = validate_apkg(breast_out, ["::1. JBL", "::2. 족보"])

report = Path(namespace["report"])
with report.open("a", encoding="utf-8") as fp:
    fp.write("\n## APKG database validation\n\n")
    fp.write("### Pediatric Surgery\n")
    for name, count in peds_validation.items():
        fp.write(f"- `{name}`: {count} cards\n")
    fp.write("\n### Breast Imaging\n")
    for name, count in breast_validation.items():
        fp.write(f"- `{name}`: {count} cards\n")
    fp.write("\n- Required subdecks: present and non-empty\n")
    fp.write("- Standardized note types: present\n")
    fp.write("- Tags: none\n")
print(report.read_text(encoding="utf-8"))
