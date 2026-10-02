"""
Estimate forest aboveground biomass (AGB) from a UAV RGB+Alpha orthomosaic.

The original DeepLiDARPlanet scripts expected Planet BGR+NIR tiles, a trained
U-Net height model, and a LiDAR wall-to-wall CHM. Those inputs are not present.
This module instead maps canopy from RGB vegetation indices and converts
fractional canopy cover to AGB (Mg/ha) with a cover-based allometric model
suitable for northern Vietnam subtropical forest.

Recalibrate AGB_CLOSED_MG_HA and COVER_EXPONENT if you have local field plots.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None


# ---------------------------------------------------------------------------
# Paths and model parameters
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
INPUT_ORTHO = ROOT / "data" / "orthomosaic.tif"
OUTPUT_DIR = ROOT / "output"

# Canopy classification (tuned on tiles from this orthomosaic)
EXG_VEG_THRESHOLD = 0.16
VARI_VEG_THRESHOLD = 0.08

# AGB = AGB_CLOSED_MG_HA * FCC ** COVER_EXPONENT * vigor
# Closed evergreen/mixed forest in northern Vietnam is typically 150-300 Mg/ha
# (VNFOREST / UN-REDD inventory ranges). Power-law cover form is used when
# canopy height is unavailable (no LiDAR, no photogrammetric CHM).
AGB_CLOSED_MG_HA = 240.0
COVER_EXPONENT = 1.48
VARI_VIGOR_LO = 0.05
VARI_VIGOR_HI = 0.40
IPCC_CARBON_FRACTION = 0.47

GRID_RES_M = 2.0
HA_RES_M = 100.0
LCA_RES_M = 0.5
MIN_LARGE_CROWN_M2 = 100.0
TILE_SIZE = 256


def meters_per_degree(lat_deg: float) -> tuple[float, float]:
    """WGS84 meters per degree of latitude and longitude at a given latitude."""
    lat = np.deg2rad(lat_deg)
    m_per_deg_lat = (
        111132.92 - 559.82 * np.cos(2.0 * lat) + 1.175 * np.cos(4.0 * lat)
    )
    m_per_deg_lon = 111412.84 * np.cos(lat) - 93.5 * np.cos(3.0 * lat)
    return float(m_per_deg_lat), float(m_per_deg_lon)


def read_geotiff_header(path: Path) -> dict:
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        height, width = int(page.shape[0]), int(page.shape[1])
        scale = page.tags["ModelPixelScaleTag"].value
        tie = page.tags["ModelTiepointTag"].value
        lon0, lat0 = float(tie[3]), float(tie[4])
        px_lon_deg, px_lat_deg = float(scale[0]), float(scale[1])
        m_per_deg_lat, m_per_deg_lon = meters_per_degree(lat0)
        return {
            "height": height,
            "width": width,
            "lon0": lon0,
            "lat0": lat0,
            "px_lon_deg": px_lon_deg,
            "px_lat_deg": px_lat_deg,
            "px_x_m": px_lon_deg * m_per_deg_lon,
            "px_y_m": px_lat_deg * m_per_deg_lat,
            "m_per_deg_lat": m_per_deg_lat,
            "m_per_deg_lon": m_per_deg_lon,
            "geokeys": tuple(page.tags["GeoKeyDirectoryTag"].value),
            "geo_ascii": page.tags["GeoAsciiParamsTag"].value,
            "geo_double": tuple(page.tags["GeoDoubleParamsTag"].value),
        }


def excess_green(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 2.0 * g - r - b


def visible_atmospherically_resistant_index(
    r: np.ndarray, g: np.ndarray, b: np.ndarray
) -> np.ndarray:
    den = g + r - b
    return np.divide(g - r, den, out=np.zeros_like(g), where=np.abs(den) > 1e-6)


def vigor_from_vari(vari: np.ndarray) -> np.ndarray:
    span = max(VARI_VIGOR_HI - VARI_VIGOR_LO, 1e-6)
    t = np.clip((vari - VARI_VIGOR_LO) / span, 0.0, 1.0)
    return 0.80 + 0.40 * t


def agb_from_cover(fcc: np.ndarray, vari: np.ndarray) -> np.ndarray:
    cover = np.clip(fcc, 0.0, 1.0)
    agb = AGB_CLOSED_MG_HA * np.power(cover, COVER_EXPONENT) * vigor_from_vari(vari)
    return agb


def decode_tile(page, filehandle, tile_index: int) -> np.ndarray:
    offset = page.dataoffsets[tile_index]
    nbytes = page.databytecounts[tile_index]
    if nbytes == 0:
        return np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    filehandle.seek(offset)
    raw = filehandle.read(nbytes)
    decoded = page.decode(raw, tile_index)
    arr = np.asarray(decoded[0] if isinstance(decoded, tuple) else decoded)
    return np.squeeze(arr)


def write_world_file(path: Path, scale_x: float, scale_y: float, lon0: float, lat0: float) -> None:
    # ESRI world file: pixel size, rotation, center of the first pixel
    lines = [
        f"{scale_x:.16e}",
        "0.0",
        "0.0",
        f"{-scale_y:.16e}",
        f"{lon0 + 0.5 * scale_x:.16f}",
        f"{lat0 - 0.5 * scale_y:.16f}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_geotiff(
    path: Path,
    array: np.ndarray,
    lon0: float,
    lat0: float,
    scale_x: float,
    scale_y: float,
    header: dict,
) -> None:
    data = np.asarray(array, dtype=np.float32)
    geokeys = header["geokeys"]
    geo_double = header["geo_double"]
    geo_ascii = header["geo_ascii"]
    if isinstance(geo_ascii, bytes):
        ascii_val = geo_ascii.decode("ascii", errors="ignore")
    else:
        ascii_val = str(geo_ascii)
    if not ascii_val.endswith("\x00"):
        ascii_val += "\x00"

    tifffile.imwrite(
        path,
        data,
        photometric="minisblack",
        planarconfig="contig",
        compression="lzw",
        extratags=[
            (33550, 12, 3, (float(scale_x), float(scale_y), 0.0), False),
            (33922, 12, 6, (0.0, 0.0, 0.0, float(lon0), float(lat0), 0.0), False),
            (34735, 3, len(geokeys), geokeys, False),
            (34736, 12, len(geo_double), geo_double, False),
            (34737, 2, len(ascii_val), ascii_val, False),
        ],
    )
    write_world_file(path.with_suffix(".tfw"), scale_x, scale_y, lon0, lat0)


def save_preview(path: Path, array: np.ndarray, title: str, cmap: str, label: str) -> None:
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(10, 8))
    masked = np.ma.masked_invalid(array)
    im = ax.imshow(masked, cmap=cmap)
    fig.colorbar(im, ax=ax, label=label, shrink=0.8)
    ax.set_title(title)
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def process_orthomosaic(ortho_path: Path, output_dir: Path) -> dict:
    ortho_path = Path(ortho_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if not ortho_path.exists():
        raise FileNotFoundError(f"Khong tim thay orthomosaic: {ortho_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Input:  {ortho_path}")
    print(f"Output: {output_dir}")
    header = read_geotiff_header(ortho_path)
    height, width = header["height"], header["width"]
    px_x_m, px_y_m = header["px_x_m"], header["px_y_m"]
    width_m = width * px_x_m
    height_m = height * px_y_m

    grid_rows = int(np.ceil(height_m / GRID_RES_M))
    grid_cols = int(np.ceil(width_m / GRID_RES_M))
    lca_rows = int(np.ceil(height_m / LCA_RES_M))
    lca_cols = int(np.ceil(width_m / LCA_RES_M))
    ha_rows = int(np.ceil(height_m / HA_RES_M))
    ha_cols = int(np.ceil(width_m / HA_RES_M))

    veg_sum = np.zeros((grid_rows, grid_cols), dtype=np.float64)
    valid_sum = np.zeros((grid_rows, grid_cols), dtype=np.float64)
    exg_sum = np.zeros((grid_rows, grid_cols), dtype=np.float64)
    vari_sum = np.zeros((grid_rows, grid_cols), dtype=np.float64)
    r_sum = np.zeros((grid_rows, grid_cols), dtype=np.float64)
    g_sum = np.zeros((grid_rows, grid_cols), dtype=np.float64)
    b_sum = np.zeros((grid_rows, grid_cols), dtype=np.float64)
    veg_lca = np.zeros((lca_rows, lca_cols), dtype=np.uint8)
    valid_lca = np.zeros((lca_rows, lca_cols), dtype=np.uint8)

    tiles_across = (width + TILE_SIZE - 1) // TILE_SIZE
    tiles_down = (height + TILE_SIZE - 1) // TILE_SIZE
    n_tiles = tiles_across * tiles_down

    print(f"Orthomosaic: {width} x {height} px, {px_x_m*100:.2f} x {px_y_m*100:.2f} cm")
    print(f"Pham vi: {width_m:.1f} x {height_m:.1f} m ({width_m * height_m / 10000:.2f} ha)")
    print(f"Toa do goc (WGS84): {header['lon0']:.6f} E, {header['lat0']:.6f} N")
    print(f"Xu ly {n_tiles} tile ({tiles_across} x {tiles_down})...")

    t0 = time.time()
    used_tiles = 0
    with tifffile.TiffFile(ortho_path) as tif:
        page = tif.pages[0]
        fh = tif.filehandle
        for ti in range(tiles_down):
            for tj in range(tiles_across):
                idx = ti * tiles_across + tj
                arr = decode_tile(page, fh, idx)
                if arr.ndim != 3 or arr.shape[-1] < 4:
                    continue

                row0 = ti * TILE_SIZE
                col0 = tj * TILE_SIZE
                h = min(arr.shape[0], height - row0)
                w = min(arr.shape[1], width - col0)
                arr = arr[:h, :w]
                alpha = arr[..., 3]
                if not np.any(alpha):
                    continue

                rgb = arr[..., :3].astype(np.float32) / 255.0
                r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
                valid = (alpha > 0).astype(np.float32)
                exg = excess_green(r, g, b)
                vari = visible_atmospherically_resistant_index(r, g, b)
                veg = (
                    (valid > 0)
                    & (exg > EXG_VEG_THRESHOLD)
                    & (vari > VARI_VEG_THRESHOLD)
                ).astype(np.float32)

                rows_m = (row0 + np.arange(h, dtype=np.float64)) * px_y_m
                cols_m = (col0 + np.arange(w, dtype=np.float64)) * px_x_m
                rr2 = np.minimum((rows_m / GRID_RES_M).astype(np.int32), grid_rows - 1)
                cc2 = np.minimum((cols_m / GRID_RES_M).astype(np.int32), grid_cols - 1)
                rr2 = np.broadcast_to(rr2[:, None], (h, w))
                cc2 = np.broadcast_to(cc2[None, :], (h, w))
                np.add.at(veg_sum, (rr2, cc2), veg)
                np.add.at(valid_sum, (rr2, cc2), valid)
                np.add.at(exg_sum, (rr2, cc2), exg * valid)
                np.add.at(vari_sum, (rr2, cc2), vari * valid)
                np.add.at(r_sum, (rr2, cc2), r * valid)
                np.add.at(g_sum, (rr2, cc2), g * valid)
                np.add.at(b_sum, (rr2, cc2), b * valid)

                rr05 = np.minimum((rows_m / LCA_RES_M).astype(np.int32), lca_rows - 1)
                cc05 = np.minimum((cols_m / LCA_RES_M).astype(np.int32), lca_cols - 1)
                rr05 = np.broadcast_to(rr05[:, None], (h, w))
                cc05 = np.broadcast_to(cc05[None, :], (h, w))
                np.maximum.at(veg_lca, (rr05, cc05), veg.astype(np.uint8))
                np.maximum.at(valid_lca, (rr05, cc05), valid.astype(np.uint8))
                used_tiles += 1

            done = (ti + 1) * tiles_across
            if (ti + 1) % 8 == 0 or ti + 1 == tiles_down:
                elapsed = time.time() - t0
                print(f"  Hang tile {ti + 1}/{tiles_down} ({done}/{n_tiles}), {elapsed:.1f}s")

    with np.errstate(divide="ignore", invalid="ignore"):
        fcc = np.divide(veg_sum, valid_sum, out=np.full_like(veg_sum, np.nan), where=valid_sum > 0)
        exg_mean = np.divide(exg_sum, valid_sum, out=np.full_like(exg_sum, np.nan), where=valid_sum > 0)
        vari_mean = np.divide(vari_sum, valid_sum, out=np.full_like(vari_sum, np.nan), where=valid_sum > 0)
        rgb_preview = np.stack(
            [
                np.divide(r_sum, valid_sum, out=np.zeros_like(r_sum), where=valid_sum > 0),
                np.divide(g_sum, valid_sum, out=np.zeros_like(g_sum), where=valid_sum > 0),
                np.divide(b_sum, valid_sum, out=np.zeros_like(b_sum), where=valid_sum > 0),
            ],
            axis=-1,
        )

    agb = np.full_like(fcc, np.nan, dtype=np.float64)
    valid_cells = np.isfinite(fcc)
    agb[valid_cells] = agb_from_cover(fcc[valid_cells], np.nan_to_num(vari_mean[valid_cells], nan=0.0))

    # 1-ha aggregation
    ha_cover, ha_agb, ha_valid = aggregate_to_block(fcc, agb, valid_sum, GRID_RES_M, HA_RES_M, ha_rows, ha_cols)

    # Large-crown area proxy (connected canopy patches >= 100 m2), no height needed
    structure = np.ones((3, 3), dtype=np.uint8)
    labels, n_labels = ndimage.label(veg_lca > 0, structure=structure)
    pixel_area = LCA_RES_M * LCA_RES_M
    lca_mask = np.zeros_like(veg_lca, dtype=np.uint8)
    if n_labels > 0:
        sizes = ndimage.sum(veg_lca > 0, labels, index=np.arange(1, n_labels + 1))
        large_ids = np.where(np.asarray(sizes) * pixel_area >= MIN_LARGE_CROWN_M2)[0] + 1
        lca_mask = np.isin(labels, large_ids).astype(np.uint8)

    lca_frac = block_fraction(lca_mask, valid_lca, LCA_RES_M, HA_RES_M, ha_rows, ha_cols)

    cell_area_ha = (GRID_RES_M * GRID_RES_M) / 10000.0
    kg_per_mg_ha_pixel = cell_area_ha * 1000.0
    n_valid = int(np.count_nonzero(valid_cells))
    stock_kg = agb[valid_cells] * kg_per_mg_ha_pixel
    total_agb_mg = float(np.sum(stock_kg) / 1000.0) if n_valid else 0.0
    mean_kg_pixel = float(np.mean(stock_kg)) if n_valid else 0.0
    mean_agb = mean_kg_pixel / kg_per_mg_ha_pixel if n_valid else 0.0
    valid_area_ha = float(n_valid * cell_area_ha)
    vegetated_area_ha = float(np.nansum(fcc) * cell_area_ha)
    mean_cover = float(np.nanmean(fcc) * 100.0) if n_valid else 0.0

    scale_x_2m = GRID_RES_M / header["m_per_deg_lon"]
    scale_y_2m = GRID_RES_M / header["m_per_deg_lat"]
    scale_x_ha = HA_RES_M / header["m_per_deg_lon"]
    scale_y_ha = HA_RES_M / header["m_per_deg_lat"]

    write_geotiff(output_dir / "canopy_cover_2m.tif", fcc * 100.0, header["lon0"], header["lat0"], scale_x_2m, scale_y_2m, header)
    write_geotiff(output_dir / "agb_Mg_ha_2m.tif", agb, header["lon0"], header["lat0"], scale_x_2m, scale_y_2m, header)
    write_geotiff(output_dir / "exg_2m.tif", exg_mean, header["lon0"], header["lat0"], scale_x_2m, scale_y_2m, header)
    write_geotiff(output_dir / "vari_2m.tif", vari_mean, header["lon0"], header["lat0"], scale_x_2m, scale_y_2m, header)
    write_geotiff(output_dir / "canopy_cover_1ha.tif", ha_cover * 100.0, header["lon0"], header["lat0"], scale_x_ha, scale_y_ha, header)
    write_geotiff(output_dir / "agb_Mg_ha_1ha.tif", ha_agb, header["lon0"], header["lat0"], scale_x_ha, scale_y_ha, header)
    write_geotiff(output_dir / "large_crown_area_pct_1ha.tif", lca_frac * 100.0, header["lon0"], header["lat0"], scale_x_ha, scale_y_ha, header)

    save_preview(output_dir / "preview_agb_2m.png", agb, "Sinh khoi tren mat dat (AGB)", "YlGn", "Mg/ha")
    save_preview(output_dir / "preview_canopy_cover_2m.png", fcc * 100.0, "Do che phu tan", "YlGn", "%")
    save_preview(output_dir / "preview_vari_2m.png", vari_mean, "VARI", "RdYlGn", "VARI")
    if plt is not None:
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.imshow(np.clip(rgb_preview, 0, 1))
        ax.set_title("Orthomosaic (2 m)")
        fig.tight_layout()
        fig.savefig(output_dir / "preview_rgb_2m.png", dpi=150)
        plt.close(fig)

    summary = {
        "input": str(ortho_path),
        "crs": "EPSG:4326 (WGS 84)",
        "origin_lon": header["lon0"],
        "origin_lat": header["lat0"],
        "pixel_size_cm": round(px_x_m * 100.0, 3),
        "extent_width_m": round(width_m, 2),
        "extent_height_m": round(height_m, 2),
        "mapped_area_ha": round(valid_area_ha, 3),
        "vegetated_area_ha": round(vegetated_area_ha, 3),
        "mean_canopy_cover_pct": round(mean_cover, 2),
        "mean_agb_Mg_ha": round(mean_agb, 2),
        "min_agb_Mg_ha": round(float(np.nanmin(agb)) if valid_cells.any() else 0.0, 2),
        "max_agb_Mg_ha": round(float(np.nanmax(agb)) if valid_cells.any() else 0.0, 2),
        "total_agb_Mg": round(total_agb_mg, 2),
        "total_carbon_Mg": round(total_agb_mg * IPCC_CARBON_FRACTION, 2),
        "agb_closed_Mg_ha": AGB_CLOSED_MG_HA,
        "cover_exponent": COVER_EXPONENT,
        "exg_threshold": EXG_VEG_THRESHOLD,
        "vari_threshold": VARI_VEG_THRESHOLD,
        "used_tiles": used_tiles,
        "elapsed_s": round(time.time() - t0, 1),
        "equation": (
            f"AGB = {AGB_CLOSED_MG_HA} * FCC^{COVER_EXPONENT} * vigor(VARI); "
            "FCC from ExG/VARI canopy mask"
        ),
    }
    write_summary_csv(output_dir / "biomass_summary.csv", summary)
    write_ha_table(output_dir / "biomass_1ha.csv", ha_cover, ha_agb, lca_frac, header, scale_x_ha, scale_y_ha)

    print("\n===== KET QUA SINH KHOI RUNG =====")
    print(f"Dien tich hop le:     {summary['mapped_area_ha']:.2f} ha")
    print(f"Dien tich co tan:     {summary['vegetated_area_ha']:.2f} ha")
    print(f"Do che phu tan TB:    {summary['mean_canopy_cover_pct']:.1f} %")
    print(f"AGB trung binh:       {summary['mean_agb_Mg_ha']:.1f} Mg/ha")
    print(f"Tong AGB:             {summary['total_agb_Mg']:.1f} tan (Mg)")
    print(f"Carbon (IPCC 0.47):   {summary['total_carbon_Mg']:.1f} tan C")
    print(f"Ket qua luu tai:      {output_dir}")
    return summary


def aggregate_to_block(
    fcc: np.ndarray,
    agb: np.ndarray,
    valid_sum: np.ndarray,
    src_res: float,
    dst_res: float,
    dst_rows: int,
    dst_cols: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    factor = int(round(dst_res / src_res))
    src_rows, src_cols = fcc.shape
    ha_cover = np.full((dst_rows, dst_cols), np.nan, dtype=np.float64)
    ha_agb = np.full((dst_rows, dst_cols), np.nan, dtype=np.float64)
    ha_valid = np.zeros((dst_rows, dst_cols), dtype=np.float64)
    for i in range(dst_rows):
        for j in range(dst_cols):
            r0, r1 = i * factor, min((i + 1) * factor, src_rows)
            c0, c1 = j * factor, min((j + 1) * factor, src_cols)
            weights = valid_sum[r0:r1, c0:c1]
            if not np.any(weights > 0):
                continue
            cover_block = fcc[r0:r1, c0:c1]
            agb_block = agb[r0:r1, c0:c1]
            mask = np.isfinite(cover_block) & (weights > 0)
            if not np.any(mask):
                continue
            w = weights[mask]
            ha_valid[i, j] = w.sum()
            ha_cover[i, j] = np.average(cover_block[mask], weights=w)
            cell_area_ha = (src_res * src_res) / 10000.0
            kg_per_mg_ha = cell_area_ha * 1000.0
            stock_kg = agb_block[mask] * kg_per_mg_ha
            mean_kg_pixel = float(np.average(stock_kg, weights=w))
            ha_agb[i, j] = mean_kg_pixel / kg_per_mg_ha
    return ha_cover, ha_agb, ha_valid


def block_fraction(
    mask: np.ndarray,
    valid: np.ndarray,
    src_res: float,
    dst_res: float,
    dst_rows: int,
    dst_cols: int,
) -> np.ndarray:
    factor = int(round(dst_res / src_res))
    src_rows, src_cols = mask.shape
    out = np.full((dst_rows, dst_cols), np.nan, dtype=np.float64)
    for i in range(dst_rows):
        for j in range(dst_cols):
            r0, r1 = i * factor, min((i + 1) * factor, src_rows)
            c0, c1 = j * factor, min((j + 1) * factor, src_cols)
            v = valid[r0:r1, c0:c1] > 0
            if not np.any(v):
                continue
            out[i, j] = mask[r0:r1, c0:c1][v].mean()
    return out


def write_summary_csv(path: Path, summary: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["parameter", "value"])
        for key, value in summary.items():
            writer.writerow([key, value])


def write_ha_table(
    path: Path,
    ha_cover: np.ndarray,
    ha_agb: np.ndarray,
    lca_frac: np.ndarray,
    header: dict,
    scale_x: float,
    scale_y: float,
) -> None:
    rows, cols = ha_cover.shape
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "row",
                "col",
                "lon",
                "lat",
                "canopy_cover_pct",
                "agb_Mg_ha",
                "large_crown_area_pct",
            ]
        )
        for i in range(rows):
            for j in range(cols):
                if not np.isfinite(ha_cover[i, j]):
                    continue
                lon = header["lon0"] + (j + 0.5) * scale_x
                lat = header["lat0"] - (i + 0.5) * scale_y
                writer.writerow(
                    [
                        i,
                        j,
                        f"{lon:.8f}",
                        f"{lat:.8f}",
                        f"{ha_cover[i, j] * 100.0:.2f}",
                        f"{ha_agb[i, j]:.2f}",
                        f"{lca_frac[i, j] * 100.0:.2f}" if np.isfinite(lca_frac[i, j]) else "",
                    ]
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Tinh sinh khoi AGB tu orthomosaic UAV RGB")
    parser.add_argument("--input", "-i", type=Path, default=INPUT_ORTHO, help="Duong dan file GeoTIFF dau vao")
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_DIR, help="Thu muc ghi ket qua dau ra")
    args = parser.parse_args()
    process_orthomosaic(args.input, args.output)


if __name__ == "__main__":
    main()
