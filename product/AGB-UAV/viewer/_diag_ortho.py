import json
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
print("data dir", (root / "data").exists(), root / "data")
print("ortho", (root / "data" / "orthomosaic.tif").exists())

url = "http://127.0.0.1:8765/overlay/ortho.png?t=1&size=512&west=105.677&south=21.119&east=105.686&north=21.127"
try:
    with urllib.request.urlopen(url) as resp:
        print("overlay status", resp.status, "len", resp.length)
except urllib.error.HTTPError as exc:
    print("overlay status", exc.code)
    print("overlay body", exc.read().decode("utf-8", "replace"))

with urllib.request.urlopen("http://127.0.0.1:8765/api/summary") as resp:
    data = json.load(resp)
for layer in data.get("layers", []):
    print(
        layer["id"],
        "file=",
        layer.get("file"),
        "error=",
        layer.get("error"),
        "crs=",
        layer.get("crs"),
        "west=",
        layer.get("west"),
        "south=",
        layer.get("south"),
        "east=",
        layer.get("east"),
        "north=",
        layer.get("north"),
        "w/h=",
        layer.get("width"),
        layer.get("height"),
    )
