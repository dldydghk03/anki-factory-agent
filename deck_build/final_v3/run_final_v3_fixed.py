from pathlib import Path

wrapper_path = Path(__file__).with_name("run_final_v3.py")
wrapper_source = wrapper_path.read_text(encoding="utf-8")

old = '''replace_once(
    r"(PEDS_PDF = download_drive\\([^\\n]+\\)\\n)",
    r"\\1PEDS_Q_PDF = download_drive(\\\"1raCcBgDpXgw3hnXSEjHnLjabkh2NgY6i\\\", SRC / \\\"peds_summary.pdf\\\")\\n",
    label="insert pediatric question source",
)
'''
new = '''_peds_source_match = re.search(r"PEDS_PDF = download_drive\\([^\\n]+\\)\\n", source)
if not _peds_source_match:
    raise RuntimeError("insert pediatric question source failed")
source = (
    source[:_peds_source_match.end()]
    + 'PEDS_Q_PDF = download_drive("1raCcBgDpXgw3hnXSEjHnLjabkh2NgY6i", SRC / "peds_summary.pdf")\\n'
    + source[_peds_source_match.end():]
)
'''

if old not in wrapper_source:
    raise RuntimeError("Expected insertion block was not found in run_final_v3.py")
wrapper_source = wrapper_source.replace(old, new, 1)

namespace = {"__file__": str(wrapper_path), "__name__": "__main__"}
exec(compile(wrapper_source, str(wrapper_path), "exec"), namespace)
