from pathlib import Path

script = Path(__file__).with_name("run_final_v2.py")
source = script.read_text(encoding="utf-8")
source = source.replace("lecture_patch = r'''", 'lecture_patch = r"""', 1)
source = source.replace("\n'''\nneedle = '# The standardized exam note type uses Korean field names. Map them explicitly\\n'", "\n\"\"\"\nneedle = '# The standardized exam note type uses Korean field names. Map them explicitly\\n'", 1)
namespace = {"__file__": str(script), "__name__": "__main__"}
exec(compile(source, str(script), "exec"), namespace)
