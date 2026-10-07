"""No file of the project starts with a BOM: Windows PowerShell 5.1 adds one (Set-Content -Encoding utf8), git
then stores it, and every later patch of that file carries an invisible change. This test catches it at once."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = ["*.py", "*.js", "*.jsx", "*.css", "*.md", "*.json", "*.html"]


def test_no_tracked_text_file_starts_with_a_bom():
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", *PATTERNS],
                           cwd=ROOT, capture_output=True, text=True).stdout.split()
    with_bom = [f for f in files if (ROOT / f).is_file() and (ROOT / f).read_bytes().startswith(b"\xef\xbb\xbf")]
    assert not with_bom, "BOM a retirer : " + ", ".join(with_bom)
