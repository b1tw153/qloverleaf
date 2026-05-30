"""Convert README.md to src/qloverleaf/static/index.html."""

from pathlib import Path

import markdown

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"
OUTPUT = ROOT / "src" / "qloverleaf" / "static" / "index.html"

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QLoverleaf</title>
</head>
<body>
{body}
</body>
</html>
"""

body = markdown.markdown(README.read_text(), extensions=["fenced_code", "tables"])
OUTPUT.write_text(TEMPLATE.format(body=body))
print(f"Written: {OUTPUT}")
