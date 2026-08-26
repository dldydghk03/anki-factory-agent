from pathlib import Path

script = Path(__file__).with_name("run_builder.py")
source = script.read_text(encoding="utf-8")

# Distinguish this verified build from every earlier package.
source = source.replace("0826_최종개선판.apkg", "0826_누락검수완료.apkg")

# Keep the cards neutral and textbook-like rather than addressing the learner.
for old, new in {
    "왕족입니다": "여러 해 반복 출제되었습니다",
    "왕족": "반복 출제",
    "꼭 기억하세요": "",
    "꼭 기억": "",
    "이 카드에서는": "",
    "익혀야 합니다": "확인합니다",
    "가져갈 한 줄": "핵심 정리",
    "여기서부터가 시험의 진짜 핵심": "",
}.items():
    source = source.replace(old, new)

namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(source, str(script), "exec"), namespace)
