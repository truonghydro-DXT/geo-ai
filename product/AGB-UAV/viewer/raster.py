"""Read and window GeoTIFFs with rasterio, keeping GTiff format/CRS/dtype."""

from __future__ import annotations

import math
import os
import threading
from pathlib import Path

# PostgreSQL/PostGIS often sets PROJ_LIB to an older proj.db and breaks rasterio.
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

import numpy as np
import rasterio

_proj_data = Path(rasterio.__file__).resolve().parent / "proj_data"
if _proj_data.exists():
    os.environ["PROJ_DATA"] = str(_proj_data)
    os.environ["PROJ_LIB"] = str(_proj_data)

from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import bounds as geom_bounds
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.warp import transform as warp_xy
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds, intersection

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "data"
ORTHO_PATH = DATA_DIR / "orthomosaic.tif"


def get_ortho_path() -> Path:
    return ORTHO_PATH


def get_output_dir() -> Path:
    return OUTPUT_DIR


def get_data_dir() -> Path:
    return DATA_DIR


def set_io_paths(ortho_path: Path | None = None, output_dir: Path | None = None) -> None:
    global OUTPUT_DIR, DATA_DIR, ORTHO_PATH
    if ortho_path is not None:
        ORTHO_PATH = Path(ortho_path)
        DATA_DIR = ORTHO_PATH.parent
    if output_dir is not None:
        OUTPUT_DIR = Path(output_dir)


WGS84 = CRS.from_epsg(4326)
MAX_WINDOW_SIDE = 2048
_LOCK = threading.Lock()

# 2 m × 2 m pixel. Raster stores density (Mg/ha); stock is computed per pixel first.
AGB_PIXEL_M = 2.0
AGB_PIXEL_AREA_M2 = AGB_PIXEL_M * AGB_PIXEL_M
AGB_PIXEL_AREA_HA = AGB_PIXEL_AREA_M2 / 10_000.0
KG_PER_MG_HA_PIXEL = AGB_PIXEL_AREA_HA * 1000.0  # 0.4 kg on a 2×2 m cell per 1 Mg/ha


def agb_stock_mg(density_mg_ha: float) -> float:
    return float(density_mg_ha) * AGB_PIXEL_AREA_HA


def agb_stock_kg(density_mg_ha: float) -> float:
    return float(density_mg_ha) * KG_PER_MG_HA_PIXEL


def resolve_raster(filename: str) -> Path:
    if filename == "orthomosaic.tif":
        path = ORTHO_PATH
    else:
        path = OUTPUT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(filename)
    return path


def raster_info(path: Path) -> dict:
    with rasterio.open(path) as src:
        bounds = src.bounds
        crs = src.crs
        finite_min = finite_max = None
        if src.count == 1 and src.width * src.height <= 2_000_000:
            data = src.read(1, masked=True)
            if np.isfinite(data).any():
                finite_min = float(np.nanmin(data.filled(np.nan)))
                finite_max = float(np.nanmax(data.filled(np.nan)))
                if np.ma.is_masked(data):
                    finite_min = float(np.nanpercentile(np.asarray(data.filled(np.nan)), 2))
                    finite_max = float(np.nanpercentile(np.asarray(data.filled(np.nan)), 98))
        return {
            "path": str(path),
            "driver": src.driver,
            "crs": crs.to_string() if crs else None,
            "epsg": crs.to_epsg() if crs else None,
            "bounds": [bounds.bottom, bounds.left, bounds.top, bounds.right],
            "west": bounds.left,
            "south": bounds.bottom,
            "east": bounds.right,
            "north": bounds.top,
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "dtype": src.dtypes[0],
            "nodata": src.nodata,
            "transform": list(src.transform),
            "vmin": finite_min,
            "vmax": finite_max,
        }


def _parse_lonlat_ring(coordinates: list) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    for item in coordinates:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            lon, lat = float(item[0]), float(item[1])
        elif isinstance(item, dict):
            lon = float(item.get("lon", item.get("lng")))
            lat = float(item.get("lat"))
        else:
            raise ValueError("Toa do polygon khong hop le")
        if not math.isfinite(lon) or not math.isfinite(lat):
            raise ValueError("Toa do polygon khong hop le")
        if ring and abs(ring[-1][0] - lon) < 1e-12 and abs(ring[-1][1] - lat) < 1e-12:
            continue
        ring.append((lon, lat))
    if len(ring) < 3:
        raise ValueError("Polygon can it nhat 3 dinh")
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    if len(ring) < 4:
        raise ValueError("Polygon can it nhat 3 dinh")
    return ring


def _ring_area_ha(ring: list[tuple[float, float]]) -> float:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    lat0 = sum(lats[:-1]) / max(len(lats) - 1, 1)
    m_per_deg_lat = 111_132.92
    m_per_deg_lon = 111_132.92 * math.cos(math.radians(lat0))
    xs = [(lon - lons[0]) * m_per_deg_lon for lon in lons]
    ys = [(lat - lats[0]) * m_per_deg_lat for lat in lats]
    acc = 0.0
    for i in range(len(xs) - 1):
        acc += xs[i] * ys[i + 1] - xs[i + 1] * ys[i]
    return abs(acc) / 2.0 / 10_000.0


def _agb_empty_stats(ring: list[tuple[float, float]], message: str) -> dict:
    return {
        "vertex_count": max(len(ring) - 1, 0),
        "pixel_count": 0,
        "pixel_m": AGB_PIXEL_M,
        "pixel_area_m2": AGB_PIXEL_AREA_M2,
        "pixel_area_ha": AGB_PIXEL_AREA_HA,
        "area_ha": _ring_area_ha(ring) if len(ring) >= 4 else 0.0,
        "valid_area_ha": 0.0,
        "mean_pixel_kg": None,
        "total_pixel_kg": 0.0,
        "mean_agb_Mg_ha": None,
        "total_agb_Mg": 0.0,
        "total_carbon_Mg": 0.0,
        "message": message,
    }


def polygon_agb_stats(path: Path, coordinates: list) -> dict:
    """Zonal AGB: raster is Mg/ha; each pixel is 2×2 m (0.0004 ha)."""
    ring = _parse_lonlat_ring(coordinates)
    geom = {"type": "Polygon", "coordinates": [ring]}
    with _LOCK:
        with rasterio.open(path) as src:
            geom_src = geom
            if src.crs and src.crs != WGS84:
                geom_src = transform_geom(WGS84, src.crs, geom, precision=8)
            west, south, east, north = geom_bounds(geom_src)
            window = from_bounds(west, south, east, north, transform=src.transform)
            window = intersection(window, Window(0, 0, src.width, src.height))
            if window.width < 1 or window.height < 1:
                return _agb_empty_stats(ring, "Vung nam ngoai pham vi raster AGB")
            data = src.read(1, window=window)
            win_transform = src.window_transform(window)
            inside = geometry_mask(
                [geom_src],
                out_shape=data.shape,
                transform=win_transform,
                invert=True,
                all_touched=False,
            )
            valid = inside & np.isfinite(data)
            if src.nodata is not None:
                valid &= data != src.nodata
            values = data[valid]
            n = int(values.size)
            area_ha = _ring_area_ha(ring)
            if n == 0:
                stats = _agb_empty_stats(ring, "Khong co pixel AGB hop le trong vung")
                stats["area_ha"] = area_ha
                return stats
            stock_kg = values.astype(np.float64) * KG_PER_MG_HA_PIXEL
            total_kg = float(np.sum(stock_kg))
            mean_kg = float(np.mean(stock_kg))
            total_agb = total_kg / 1000.0
            mean_agb = mean_kg / KG_PER_MG_HA_PIXEL
            valid_area_ha = n * AGB_PIXEL_AREA_HA
            return {
                "vertex_count": len(ring) - 1,
                "pixel_count": n,
                "pixel_m": AGB_PIXEL_M,
                "pixel_area_m2": AGB_PIXEL_AREA_M2,
                "pixel_area_ha": AGB_PIXEL_AREA_HA,
                "area_ha": area_ha,
                "valid_area_ha": valid_area_ha,
                "mean_pixel_kg": mean_kg,
                "total_pixel_kg": total_kg,
                "mean_agb_Mg_ha": mean_agb,
                "total_agb_Mg": total_agb,
                "total_carbon_Mg": total_agb * 0.47,
            }


def sample_lonlat(path: Path, lon: float, lat: float) -> float | None:
    with rasterio.open(path) as src:
        xs, ys = [lon], [lat]
        if src.crs and src.crs != WGS84:
            xs, ys = warp_xy(WGS84, src.crs, xs, ys)
        row, col = src.index(xs[0], ys[0])
        if row < 0 or col < 0 or row >= src.height or col >= src.width:
            return None
        window = Window(col, row, 1, 1)
        value = src.read(1, window=window, boundless=False)[0, 0]
        if src.nodata is not None and value == src.nodata:
            return None
        if not np.isfinite(value):
            return None
        return float(value)


def window_geotiff(
    path: Path,
    west: float,
    south: float,
    east: float,
    north: float,
    max_side: int = MAX_WINDOW_SIDE,
) -> bytes:
    """Clip a geographic window and write a GeoTIFF that keeps CRS/dtype/bands."""
    with _LOCK:
        with rasterio.open(path) as src:
            src_bounds = src.bounds
            west = max(west, src_bounds.left)
            south = max(south, src_bounds.bottom)
            east = min(east, src_bounds.right)
            north = min(north, src_bounds.top)
            if east <= west or north <= south:
                raise ValueError("Cua so nam ngoai pham vi GeoTIFF")

            window = from_bounds(west, south, east, north, transform=src.transform)
            window = intersection(window, Window(0, 0, src.width, src.height))
            if window.width < 1 or window.height < 1:
                raise ValueError("Cua so rong")

            win_bounds = src.window_bounds(window)
            native_w = max(1, int(round(window.width)))
            native_h = max(1, int(round(window.height)))
            scale = min(1.0, max_side / max(native_w, native_h))
            out_w = max(1, int(round(native_w * scale)))
            out_h = max(1, int(round(native_h * scale)))
            resampling = Resampling.bilinear if src.count >= 3 else Resampling.nearest
            data = src.read(
                window=window,
                out_shape=(src.count, out_h, out_w),
                resampling=resampling,
                boundless=False,
            )
            transform = transform_from_bounds(*win_bounds, width=out_w, height=out_h)
            profile = src.profile.copy()
            profile.update(
                {
                    "driver": "GTiff",
                    "height": out_h,
                    "width": out_w,
                    "count": src.count,
                    "dtype": src.dtypes[0],
                    "crs": src.crs,
                    "transform": transform,
                    "tiled": False,
                    "compress": "lzw",
                    "interleave": src.profile.get("interleave", "pixel"),
                }
            )
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)
            with MemoryFile() as memfile:
                with memfile.open(**profile) as dst:
                    dst.write(data)
                    if src.colorinterp:
                        try:
                            dst.colorinterp = src.colorinterp
                        except ValueError:
                            pass
                return memfile.read()


def read_geotiff_bytes(path: Path) -> bytes:
    return path.read_bytes()


YLG = np.array([[247, 241, 200], [157, 206, 107], [31, 107, 58]], dtype=np.float32)
RDYLG = np.array([[165, 0, 38], [254, 224, 139], [26, 152, 80]], dtype=np.float32)


def _colorize(
    band: np.ndarray,
    cmap: str,
    vmin: float | None = None,
    vmax: float | None = None,
) -> np.ndarray:
    finite = np.isfinite(band)
    if not finite.any():
        return np.zeros((*band.shape, 4), dtype=np.uint8)
    if vmin is None or vmax is None or not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        vmin = float(np.nanpercentile(band[finite], 2))
        vmax = float(np.nanpercentile(band[finite], 98))
    span = max(float(vmax) - float(vmin), 1e-6)
    t = np.clip((band - float(vmin)) / span, 0.0, 1.0)
    stops = RDYLG if cmap == "rdylgn" else YLG
    idx = np.where(t < 0.5, 0, 1)
    local = np.where(t < 0.5, t * 2.0, (t - 0.5) * 2.0)
    rgb = stops[idx] + (stops[np.minimum(idx + 1, len(stops) - 1)] - stops[idx]) * local[..., None]
    rgba = np.zeros((*band.shape, 4), dtype=np.uint8)
    rgba[..., :3] = np.nan_to_num(rgb, nan=0.0).astype(np.uint8)
    rgba[..., 3] = np.where(finite, 220, 0).astype(np.uint8)
    return rgba


def overlay_png(
    path: Path,
    cmap: str = "ylgn",
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    max_side: int = MAX_WINDOW_SIDE,
    vmin: float | None = None,
    vmax: float | None = None,
) -> bytes:
    """Render a GeoTIFF window to PNG for Leaflet, using rasterio."""
    from PIL import Image

    max_side = max(256, min(int(max_side), 4096))
    with _LOCK:
        with rasterio.open(path) as src:
            bounds = src.bounds
            west = bounds.left if west is None else max(west, bounds.left)
            south = bounds.bottom if south is None else max(south, bounds.bottom)
            east = bounds.right if east is None else min(east, bounds.right)
            north = bounds.top if north is None else min(north, bounds.top)
            if east <= west or north <= south:
                raise ValueError("Cua so nam ngoai pham vi GeoTIFF")
            window = from_bounds(west, south, east, north, transform=src.transform)
            window = intersection(window, Window(0, 0, src.width, src.height))
            native_w = max(1, int(round(window.width)))
            native_h = max(1, int(round(window.height)))
            longest = max(native_w, native_h)
            is_rgb = src.count >= 3 or cmap == "rgb"
            if is_rgb:
                scale = min(1.0, max_side / longest)
                resampling = Resampling.nearest if scale >= 0.92 else Resampling.bilinear
            else:
                scale = max_side / longest
                resampling = Resampling.nearest
            out_w = max(1, int(round(native_w * scale)))
            out_h = max(1, int(round(native_h * scale)))
            data = src.read(
                window=window,
                out_shape=(src.count, out_h, out_w),
                resampling=resampling,
                boundless=False,
            )
            band_count = src.count
    if band_count >= 3 or cmap == "rgb":
        rgb = np.transpose(data[:3], (1, 2, 0))
        if rgb.dtype != np.uint8:
            finite = np.isfinite(rgb)
            stretched = np.zeros_like(rgb, dtype=np.uint8)
            if finite.any():
                lo = np.nanpercentile(rgb, 2)
                hi = max(float(np.nanpercentile(rgb, 98)), lo + 1e-6)
                stretched = np.clip((rgb - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
            rgb = stretched
        if data.shape[0] >= 4:
            alpha = data[3]
            if alpha.dtype != np.uint8:
                alpha = np.where(np.isfinite(alpha) & (alpha > 0), 255, 0).astype(np.uint8)
            image = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
        else:
            image = Image.fromarray(rgb, "RGB")
    else:
        image = Image.fromarray(
            _colorize(data[0].astype(np.float32), cmap, vmin=vmin, vmax=vmax),
            "RGBA",
        )
    import io

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
