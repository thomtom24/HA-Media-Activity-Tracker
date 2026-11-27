"""Validate release identity and required package assets."""
import json
import os
from pathlib import Path
import struct

root = Path(__file__).resolve().parents[1]
component = root / "custom_components/media_activity_tracker"
manifest = json.loads((component / "manifest.json").read_text())
version = manifest["version"]
assert f'CARD_VERSION = "{version}"' in (component / "card_resource.py").read_text()
assert f"Media Activity Card {version}" in (component / "www/ha-media-activity-card.js").read_text()
assert f"## v{version}" in (root / "CHANGELOG.md").read_text()
for filename, size in (("icon.png", 256), ("icon@2x.png", 512)):
    data = (component / "brand" / filename).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (size, size)
if os.getenv("GITHUB_REF_TYPE") == "tag":
    assert os.getenv("GITHUB_REF_NAME") == f"v{version}", "Release tag and manifest differ"
print("Release identity and brand assets verified")
