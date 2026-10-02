import os
import zipfile
from pathlib import Path

src = Path(r"D:\NEW.WORK\geoai-sattelite_5.6\dist\qgis_geoai_satellite")
dst = Path(r"D:\NEW.WORK\geoai-sattelite_5.6\demo\qgis_geoai_satellite.zip")

if dst.exists():
    dst.unlink()

with zipfile.ZipFile(dst, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src):
        for f in files:
            path = Path(root) / f
            arcname = path.relative_to(src)
            zf.write(path, arcname)
print('created', dst)
