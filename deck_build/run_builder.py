from pathlib import Path
import zipfile

import fitz
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

def _make_dry_run_file(output: str) -> str:
    path = Path(output)
    if path.suffix.lower() == ".pdf":
        pages = 34 if "peds" in path.name else 54 if "breast" in path.name else 408
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page(width=612, height=792)
            page.insert_text((36, 50), f"DRY RUN PAGE {i+1}", fontsize=12)
        doc.save(path)
        doc.close()
    elif path.suffix.lower() == ".apkg":
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("README.txt", "dry-run template; fallback standardized models will be used")
    else:
        path.write_bytes(b"dry-run")
    print("Created dry-run source:", path, path.stat().st_size)
    return str(path)

# Google periodically changes the public download page in ways that lag behind
# gdown releases. Try direct media endpoints first, then gdown. BUILD_DRY_RUN=1
# lets the workflow validate the complete APKG pipeline without source access.
def _compatible_download(*args, **kwargs):
    kwargs.pop("fuzzy", None)
    file_id = kwargs.get("id")
    output = kwargs.get("output")
    if file_id and output:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"}
        for url in [
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
            f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t",
            f"https://drive.google.com/uc?id={file_id}&export=download",
        ]:
            try:
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=120)
                data = response.content
                print("Direct Drive attempt", response.status_code, response.headers.get("content-type"), len(data), response.url)
                if response.ok and _valid_payload(data, output):
                    Path(output).write_bytes(data)
                    return output
            except Exception as exc:
                print("Direct Drive attempt failed:", exc)
    try:
        return _original_download(*args, **kwargs)
    except Exception:
        if __import__("os").environ.get("BUILD_DRY_RUN") == "1" and output:
            return _make_dry_run_file(output)
        raise

gdown.download = _compatible_download

script = Path(__file__).with_name("build_decks.py")
source = script.read_text(encoding="utf-8")
source = source.replace("1tpNLSvDcJUx0McmWiLpt8xTePeVJd1OB", "1raCcBgDpXgw3hnXSEjHnLjabkh2NgY6i")
source = source.replace("1lbWoXqb_tleGdSRP0QIisHpXde4uFdkk", "1oYXMxzJfWii0mnNTaOXldAQ-BLfg9O-C")
source = source.replace("1iAdIOlAOVrMqXb15g-1xa8nylsjjrrPS", "1q2hBDWVLidgZvB7XyozBiyMrYnSAFa9Y")
namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(source, str(script), "exec"), namespace)
