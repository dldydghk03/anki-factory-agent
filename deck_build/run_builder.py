from pathlib import Path

import genanki
import gdown
import requests

# Compatibility across genanki releases.
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

# Google periodically changes the public download page in ways that lag behind
# gdown releases. Try the current direct media endpoints first, then fall back.
def _compatible_download(*args, **kwargs):
    kwargs.pop("fuzzy", None)
    file_id = kwargs.get("id")
    output = kwargs.get("output")
    if file_id and output:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"}
        urls = [
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
            f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t",
            f"https://drive.google.com/uc?id={file_id}&export=download",
        ]
        for url in urls:
            try:
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=120)
                data = response.content
                print("Direct Drive attempt", response.status_code, response.headers.get("content-type"), len(data), response.url)
                if response.ok and _valid_payload(data, output):
                    Path(output).write_bytes(data)
                    return output
            except Exception as exc:
                print("Direct Drive attempt failed:", exc)
    return _original_download(*args, **kwargs)

gdown.download = _compatible_download

script = Path(__file__).with_name("build_decks.py")
source = script.read_text(encoding="utf-8")
source = source.replace("1tpNLSvDcJUx0McmWiLpt8xTePeVJd1OB", "1raCcBgDpXgw3hnXSEjHnLjabkh2NgY6i")
source = source.replace("1lbWoXqb_tleGdSRP0QIisHpXde4uFdkk", "1oYXMxzJfWii0mnNTaOXldAQ-BLfg9O-C")
source = source.replace("1iAdIOlAOVrMqXb15g-1xa8nylsjjrrPS", "1q2hBDWVLidgZvB7XyozBiyMrYnSAFa9Y")
namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(source, str(script), "exec"), namespace)
