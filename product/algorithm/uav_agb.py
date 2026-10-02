"""Flask blueprint that mounts the AGB-UAV viewer under /uav."""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parents[2]
UAV_ROOT = BASE_DIR / "product" / "AGB-UAV"
UAV_VIEWER = UAV_ROOT / "viewer"
UAV_STATIC = UAV_VIEWER / "static"

if str(UAV_VIEWER) not in sys.path:
    sys.path.insert(0, str(UAV_VIEWER))

import server as uav_server  # noqa: E402
from raster import (  # noqa: E402
    AGB_PIXEL_AREA_HA,
    AGB_PIXEL_AREA_M2,
    AGB_PIXEL_M,
    agb_stock_kg,
    agb_stock_mg,
    get_data_dir,
    get_output_dir,
    overlay_png,
    polygon_agb_stats,
    read_geotiff_bytes,
    resolve_raster,
    sample_lonlat,
    window_geotiff,
)

uav_bp = Blueprint("uav_agb", __name__, url_prefix="/uav")


def _prefix_layers(layers: list[dict]) -> list[dict]:
    for item in layers:
        layer_id = item.get("id")
        if layer_id:
            item["geotiffUrl"] = f"/uav/geotiff/{layer_id}"
            item["overlayUrl"] = f"/uav/overlay/{layer_id}.png"
    return layers


def _payload_with_layers(extra: dict | None = None) -> dict:
    payload = {
        "summary": uav_server.read_summary(),
        "layers": _prefix_layers(uav_server.layer_payload()),
        **uav_server._paths_payload(),
    }
    if extra:
        payload.update(extra)
    return payload


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@uav_bp.route("/")
def uav_index():
    return send_from_directory(UAV_STATIC, "index.html")


@uav_bp.route("/static/<path:filename>")
def uav_static(filename: str):
    return send_from_directory(UAV_STATIC, filename)


@uav_bp.route("/output/<path:filename>")
def uav_output(filename: str):
    output_dir = get_output_dir().resolve()
    target = (output_dir / filename).resolve()
    if not target.is_file() or not _is_relative_to(target, output_dir):
        return _json_error("File not found", 404)
    mime = "image/tiff" if target.suffix.lower() in {".tif", ".tiff"} else None
    return send_from_directory(output_dir, filename, mimetype=mime)


@uav_bp.route("/api/summary")
def api_summary():
    return jsonify(_payload_with_layers())


@uav_bp.route("/api/cells")
def api_cells():
    return jsonify({"cells": uav_server.read_cells(), **uav_server._paths_payload()})


@uav_bp.route("/api/paths", methods=["GET", "POST"])
def api_paths():
    if request.method == "GET":
        return jsonify(uav_server._paths_payload())
    try:
        payload = request.get_json(silent=True) or {}
        paths = uav_server.apply_io_paths(
            payload.get("input"),
            payload.get("output"),
            require_output=True,
        )
    except (ValueError, OSError, TypeError) as exc:
        return jsonify({"error": str(exc), **uav_server._paths_payload()})
    return jsonify(paths)


@uav_bp.route("/api/value")
def api_value():
    layer_id = request.args.get("layer") or "agb_2m"
    spec = uav_server._layer_spec(layer_id)
    if spec is None:
        return jsonify({"error": "Khong co lop"})
    try:
        lon = float(request.args.get("lon", ""))
        lat = float(request.args.get("lat", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "Toa do khong hop le"})
    try:
        value = sample_lonlat(resolve_raster(spec["file"]), lon, lat)
    except Exception as exc:
        return jsonify({"error": str(exc)})
    payload = {
        "layer": layer_id,
        "file": spec["file"],
        "lon": lon,
        "lat": lat,
        "value": value,
        "unit": spec["unit"],
    }
    if layer_id == "agb_2m" and value is not None:
        payload.update(
            {
                "pixel_m": AGB_PIXEL_M,
                "pixel_area_m2": AGB_PIXEL_AREA_M2,
                "pixel_area_ha": AGB_PIXEL_AREA_HA,
                "pixel_kg": agb_stock_kg(value),
                "pixel_Mg": agb_stock_mg(value),
            }
        )
    return jsonify(payload)


@uav_bp.route("/api/run-biomass", methods=["GET", "POST"])
def api_run_biomass():
    if request.method == "GET":
        return jsonify(uav_server._job_snapshot())
    try:
        payload = request.get_json(silent=True) or {}
        result = uav_server.start_biomass_job(payload.get("input"), payload.get("output"))
    except (ValueError, TypeError) as exc:
        result = {
            "started": False,
            "running": False,
            "returncode": -1,
            "message": str(exc),
            "log": "",
            **uav_server._paths_payload(),
        }
    return jsonify(result)


@uav_bp.route("/api/browse", methods=["POST"])
def api_browse():
    try:
        payload = request.get_json(silent=True) or {}
        kind = payload.get("kind") or "file"
        initial = payload.get("initial") or payload.get("path")
        result = uav_server.browse_path(str(kind), initial if isinstance(initial, str) else None)
    except (ValueError, TypeError) as exc:
        result = {"error": str(exc)}
    return jsonify(result)


@uav_bp.route("/api/polygon-stats", methods=["POST"])
def api_polygon_stats():
    payload = request.get_json(silent=True) or {}
    coordinates = payload.get("coordinates") or payload.get("polygon")
    if not isinstance(coordinates, list):
        return jsonify({"error": "Thieu toa do polygon"})
    if len(coordinates) > 500:
        return jsonify({"error": "Polygon qua nhieu dinh"})
    spec = uav_server._layer_spec("agb_2m")
    if spec is None:
        return jsonify({"error": "Khong co lop AGB"})
    try:
        stats = polygon_agb_stats(resolve_raster(spec["file"]), coordinates)
    except Exception as exc:
        return jsonify({"error": str(exc)})
    stats["layer"] = spec["id"]
    stats["file"] = spec["file"]
    stats["unit"] = spec["unit"]
    return jsonify(stats)


@uav_bp.route("/geotiff/<layer_id>")
def uav_geotiff(layer_id: str):
    spec = uav_server._layer_spec(layer_id)
    if spec is None:
        return _json_error("Khong co lop GeoTIFF", 404)
    try:
        path = resolve_raster(spec["file"])
        query = request.args
        if spec.get("windowed") and {"west", "south", "east", "north"} <= set(query):
            data = window_geotiff(
                path,
                west=float(query["west"]),
                south=float(query["south"]),
                east=float(query["east"]),
                north=float(query["north"]),
                max_side=int(query.get("size", 2048)),
            )
        else:
            data = read_geotiff_bytes(path)
    except Exception as exc:
        return _json_error(str(exc))
    return Response(data, mimetype="image/tiff")


@uav_bp.route("/overlay/<layer_id>.png")
def uav_overlay(layer_id: str):
    spec = uav_server._layer_spec(layer_id)
    if spec is None:
        return _json_error("Khong co lop", 404)
    kwargs = {"cmap": spec.get("cmap") or "ylgn"}
    query = request.args
    if {"west", "south", "east", "north"} <= set(query):
        kwargs.update(
            west=float(query["west"]),
            south=float(query["south"]),
            east=float(query["east"]),
            north=float(query["north"]),
        )
    if query.get("size"):
        kwargs["max_side"] = int(query["size"])
    if query.get("vmin") and query.get("vmax"):
        kwargs["vmin"] = float(query["vmin"])
        kwargs["vmax"] = float(query["vmax"])
    try:
        data = overlay_png(resolve_raster(spec["file"]), **kwargs)
    except Exception as exc:
        return _json_error(str(exc))
    return Response(data, mimetype="image/png")


@uav_bp.route("/basemap/<int:z>/<int:x>/<int:y>.png")
def uav_basemap(z: int, x: int, y: int):
    cache = uav_server.TILE_CACHE / str(z) / str(x) / f"{y}.png"
    if cache.exists():
        return Response(cache.read_bytes(), mimetype="image/png")
    for template in uav_server.BASEMAP_SOURCES:
        url = template.format(z=z, x=x, y=y)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "GIS-GeoAI-uav-viewer/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            if data[:4] == b"\x89PNG" or data[:2] == b"\xff\xd8":
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
                return Response(data, mimetype="image/png")
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    fallback = UAV_STATIC / "vendor" / "empty-tile.png"
    if fallback.exists():
        return Response(fallback.read_bytes(), mimetype="image/png")
    return _json_error("Khong tai duoc nen ban do", 502)
