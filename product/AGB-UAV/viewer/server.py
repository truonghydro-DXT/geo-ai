"""Local GeoTIFF viewer backed by rasterio. Serves original GTiff bytes.
D:\WORK\AGB-UAV\venv\Scripts\python.exe -u D:\WORK\AGB-UAV\viewer\server.py
D:\WORK\AGB-UAV\run_agb.bat
"""

from __future__ import annotations

import csv
import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from raster import (
    AGB_PIXEL_AREA_HA,
    AGB_PIXEL_AREA_M2,
    AGB_PIXEL_M,
    agb_stock_kg,
    agb_stock_mg,
    get_data_dir,
    get_ortho_path,
    get_output_dir,
    overlay_png,
    polygon_agb_stats,
    raster_info,
    read_geotiff_bytes,
    resolve_raster,
    sample_lonlat,
    set_io_paths,
    window_geotiff,
)

TILE_CACHE = Path(__file__).resolve().parent / ".tilecache" / "basemap"
# Public OSM mirrors — no API key. Official tile.openstreetmap.org is blocked here.
BASEMAP_SOURCES = [
    "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
    "https://a.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png",
    "https://b.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png",
    "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
    "https://tile.opentopomap.org/{z}/{x}/{y}.png",
]

STATIC_DIR = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = ROOT / "venv" / "Scripts" / "python.exe"
BIOMASS_SCRIPT = ROOT / "Modelling" / "Biomass_analysis.py"
HOST = "0.0.0.0"
PORT = 8765

_job_lock = threading.Lock()
_job = {
    "running": False,
    "log": "",
    "returncode": None,
    "message": "",
}

_BROWSE_SCRIPT = r"""
import sys
import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
kind = sys.argv[1]
initial = sys.argv[2] if len(sys.argv) > 2 else ""
if kind == "dir":
    path = filedialog.askdirectory(title="Chon thu muc output", initialdir=initial or None)
else:
    path = filedialog.askopenfilename(
        title="Chon file orthomosaic",
        initialdir=initial or None,
        filetypes=[("GeoTIFF", "*.tif"), ("TIFF", "*.tiff"), ("Tat ca", "*.*")],
    )
print(path or "", end="")
"""


def _paths_payload() -> dict:
    return {
        "input": str(get_ortho_path()),
        "output": str(get_output_dir()),
    }


def _clean_path_text(raw: str | None) -> str:
    return str(raw or "").strip().strip('"').strip("'")


def _resolved_path(raw: str | None) -> Path:
    text = _clean_path_text(raw)
    if not text:
        raise ValueError("Thieu duong dan")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def apply_io_paths(
    input_raw: str | None,
    output_raw: str | None,
    *,
    require_input: bool = False,
    create_output: bool = False,
    require_output: bool = False,
) -> dict:
    ortho = get_ortho_path()
    out_dir = get_output_dir()

    if _clean_path_text(input_raw):
        candidate = _resolved_path(input_raw)
        if candidate.exists():
            if not candidate.is_file():
                raise ValueError(f"Input khong phai file: {candidate}")
            if candidate.suffix.lower() not in {".tif", ".tiff"}:
                raise ValueError("Input phai la file GeoTIFF (.tif)")
            ortho = candidate
        elif require_input:
            raise ValueError(f"Khong tim thay file input: {candidate}")

    if _clean_path_text(output_raw):
        candidate = _resolved_path(output_raw)
        if candidate.exists() and candidate.is_file():
            raise ValueError(f"Output phai la thu muc, khong phai file: {candidate}")
        if create_output:
            candidate.mkdir(parents=True, exist_ok=True)
        if require_output and not candidate.is_dir():
            raise ValueError(f"Khong tim thay thu muc output: {candidate}")
        out_dir = candidate

    if require_input and not ortho.is_file():
        raise ValueError(f"Khong tim thay file input: {ortho}")
    if require_output and not out_dir.is_dir():
        raise ValueError(f"Khong tim thay thu muc output: {out_dir}")

    set_io_paths(ortho, out_dir)
    return _paths_payload()


def _job_snapshot() -> dict:
    with _job_lock:
        log = _job["log"]
        tail = "\n".join(log.splitlines()[-8:])
        payload = {
            "running": _job["running"],
            "returncode": _job["returncode"],
            "message": _job["message"],
            "log": tail,
        }
    return payload | _paths_payload()


def browse_path(kind: str, initial: str | None = None) -> dict:
    if kind not in {"file", "dir"}:
        return {"error": "Loai chon khong hop le"}
    python = PYTHON_EXE if PYTHON_EXE.exists() else Path(sys.executable)
    start = _clean_path_text(initial)
    if not start:
        start = str(get_ortho_path().parent if kind == "file" else get_output_dir())
    else:
        hint = Path(start)
        if hint.is_file():
            start = str(hint.parent)
    try:
        completed = subprocess.run(
            [str(python), "-c", _BROWSE_SCRIPT, kind, start],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            cwd=str(ROOT),
        )
    except Exception as exc:
        return {"error": str(exc)}
    if completed.returncode not in (0, None) and not (completed.stdout or "").strip():
        err = (completed.stderr or "").strip() or f"Loi chon duong dan (ma {completed.returncode})"
        return {"error": err}
    path = (completed.stdout or "").strip()
    if not path:
        return {"cancelled": True, "path": ""}
    return {"path": path}


def _run_biomass_job(input_path: str, output_path: str) -> None:
    python = PYTHON_EXE if PYTHON_EXE.exists() else Path(sys.executable)
    try:
        proc = subprocess.Popen(
            [str(python), "-u", str(BIOMASS_SCRIPT), "--input", input_path, "--output", output_path],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            with _job_lock:
                _job["log"] += line
                _job["message"] = line.strip() or _job["message"]
        code = proc.wait()
        with _job_lock:
            _job["returncode"] = code
            _job["running"] = False
            _job["message"] = "Hoàn thành" if code == 0 else f"Lỗi (mã {code})"
    except Exception as exc:
        with _job_lock:
            _job["running"] = False
            _job["returncode"] = -1
            _job["message"] = str(exc)
            _job["log"] += f"\n{exc}\n"


def start_biomass_job(input_raw: str | None = None, output_raw: str | None = None) -> dict:
    try:
        paths = apply_io_paths(input_raw, output_raw, require_input=True, create_output=True)
    except (ValueError, OSError) as exc:
        return {
            "started": False,
            "running": False,
            "returncode": -1,
            "message": str(exc),
            "log": "",
            **_paths_payload(),
        }
    with _job_lock:
        if _job["running"]:
            return _job_snapshot() | {"started": False}
        _job.update(
            running=True,
            log=f"Input: {paths['input']}\nOutput: {paths['output']}\n",
            returncode=None,
            message="Đang chạy Biomass_analysis.py...",
        )
    threading.Thread(
        target=_run_biomass_job,
        args=(paths["input"], paths["output"]),
        daemon=True,
    ).start()
    return _job_snapshot() | {"started": True}

LAYERS = [
    {
        "id": "ortho",
        "title": "Orthomosaic RGB",
        "file": "orthomosaic.tif",
        "windowed": True,
        "unit": "",
        "description": "GeoTIFF UAV RGB+Alpha, CRS giu nguyen",
        "cmap": "rgb",
    },
    {
        "id": "agb_2m",
        "title": "AGB - Sinh khối",
        "file": "agb_Mg_ha_2m.tif",
        "windowed": False,
        "unit": "Mg/ha",
        "description": "Sinh khoi tren mat dat",
        "cmap": "ylgn",
    },
    {
        "id": "cover_2m",
        "title": "Độ che phủ",
        "file": "canopy_cover_2m.tif",
        "windowed": False,
        "unit": "%",
        "description": "GeoTIFF float32 do che phu tan",
        "cmap": "ylgn",
    },
    {
        "id": "vari_2m",
        "title": "Chỉ số VARI",
        "file": "vari_2m.tif",
        "windowed": False,
        "unit": "VARI",
        "description": "GeoTIFF float32 VARI",
        "cmap": "rdylgn",
    },
    {
        "id": "exg_2m",
        "title": "Chỉ số ExG",
        "file": "exg_2m.tif",
        "windowed": False,
        "unit": "ExG",
        "description": "GeoTIFF float32 Excess Green",
        "cmap": "rdylgn",
    },
]


def read_summary() -> dict:
    path = get_output_dir() / "biomass_summary.csv"
    data = {}
    if not path.exists():
        return data
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            data[row["parameter"]] = row["value"]
    return data


def read_cells() -> list[dict]:
    path = get_output_dir() / "biomass_1ha.csv"
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "row": int(row["row"]),
                    "col": int(row["col"]),
                    "lon": float(row["lon"]),
                    "lat": float(row["lat"]),
                    "canopy_cover_pct": float(row["canopy_cover_pct"]),
                    "agb_Mg_ha": float(row["agb_Mg_ha"]),
                    "large_crown_area_pct": float(row["large_crown_area_pct"])
                    if row.get("large_crown_area_pct")
                    else None,
                }
            )
    return rows


def layer_payload() -> list[dict]:
    layers = []
    for spec in LAYERS:
        item = dict(spec)
        try:
            info = raster_info(resolve_raster(spec["file"]))
            item.update(info)
        except Exception as exc:
            item["error"] = str(exc)
            item["bounds"] = [21.119, 105.677, 21.127, 105.686]
            item["south"], item["west"], item["north"], item["east"] = item["bounds"]
        item["geotiffUrl"] = f"/geotiff/{spec['id']}"
        item["overlayUrl"] = f"/overlay/{spec['id']}.png"
        layers.append(item)
    return layers


def _layer_spec(layer_id: str) -> dict | None:
    return next((item for item in LAYERS if item["id"] == layer_id), None)


class ViewerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            self._send_file(STATIC_DIR / path[len("/static/") :])
            return
        if path.startswith("/output/"):
            name = path[len("/output/") :]
            ctype = "image/tiff" if name.lower().endswith(".tif") else None
            self._send_file(get_output_dir() / name, ctype)
            return
        if path == "/api/summary":
            self._send_json({"summary": read_summary(), "layers": layer_payload(), **_paths_payload()})
            return
        if path == "/api/cells":
            self._send_json({"cells": read_cells(), **_paths_payload()})
            return
        if path == "/api/paths":
            self._send_json(_paths_payload())
            return
        if path == "/api/value":
            self._send_json(self._sample(query))
            return
        if path == "/api/run-biomass":
            self._send_json(_job_snapshot())
            return
        if path.startswith("/geotiff/"):
            self._send_geotiff(path[len("/geotiff/") :], query)
            return
        if path.startswith("/overlay/") and path.endswith(".png"):
            self._send_overlay(path[len("/overlay/") : -4], query)
            return
        if path.startswith("/basemap/"):
            self._send_basemap(path)
            return

        self._send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/run-biomass":
            try:
                payload = self._read_json(optional=True)
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                self._send_json({"started": False, "running": False, "returncode": -1, "message": str(exc), "log": "", **_paths_payload()})
                return
            self._send_json(start_biomass_job(payload.get("input"), payload.get("output")))
            return
        if path == "/api/paths":
            try:
                payload = self._read_json()
                paths = apply_io_paths(
                    payload.get("input"),
                    payload.get("output"),
                    require_output=True,
                )
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
                self._send_json({"error": str(exc), **_paths_payload()})
                return
            self._send_json(paths)
            return
        if path == "/api/browse":
            try:
                payload = self._read_json(optional=True)
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                self._send_json({"error": str(exc)})
                return
            kind = payload.get("kind") or "file"
            initial = payload.get("initial") or payload.get("path")
            self._send_json(browse_path(str(kind), initial if isinstance(initial, str) else None))
            return
        if path == "/api/polygon-stats":
            self._send_json(self._polygon_stats())
            return
        self._send_error(404, "Not found")

    def _read_json(self, optional: bool = False) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            if optional:
                return {}
            raise ValueError("JSON khong hop le")
        if length > 256_000:
            raise ValueError("JSON khong hop le")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON khong hop le")
        return data

    def _polygon_stats(self) -> dict:
        try:
            payload = self._read_json()
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"error": str(exc)}
        coordinates = payload.get("coordinates") or payload.get("polygon")
        if not isinstance(coordinates, list):
            return {"error": "Thieu toa do polygon"}
        if len(coordinates) > 500:
            return {"error": "Polygon qua nhieu dinh"}
        spec = _layer_spec("agb_2m")
        if spec is None:
            return {"error": "Khong co lop AGB"}
        try:
            stats = polygon_agb_stats(resolve_raster(spec["file"]), coordinates)
        except Exception as exc:
            return {"error": str(exc)}
        stats["layer"] = spec["id"]
        stats["file"] = spec["file"]
        stats["unit"] = spec["unit"]
        return stats

    def _sample(self, query: dict) -> dict:
        layer_id = (query.get("layer") or ["agb_2m"])[0]
        spec = _layer_spec(layer_id)
        if spec is None:
            return {"error": "Khong co lop"}
        try:
            lon = float((query.get("lon") or [""])[0])
            lat = float((query.get("lat") or [""])[0])
        except ValueError:
            return {"error": "Toa do khong hop le"}
        value = sample_lonlat(resolve_raster(spec["file"]), lon, lat)
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
        return payload

    def _send_geotiff(self, layer_id: str, query: dict) -> None:
        spec = _layer_spec(layer_id)
        if spec is None:
            self._send_error(404, "Khong co lop GeoTIFF")
            return
        path = resolve_raster(spec["file"])
        try:
            if spec.get("windowed") and {"west", "south", "east", "north"} <= set(query):
                data = window_geotiff(
                    path,
                    west=float(query["west"][0]),
                    south=float(query["south"][0]),
                    east=float(query["east"][0]),
                    north=float(query["north"][0]),
                    max_side=int(query.get("size", [2048])[0]),
                )
            else:
                data = read_geotiff_bytes(path)
        except Exception as exc:
            self._send_error(400, str(exc))
            return
        self._send_bytes(data, "image/tiff")

    def _send_overlay(self, layer_id: str, query: dict) -> None:
        spec = _layer_spec(layer_id)
        if spec is None:
            self._send_error(404, "Khong co lop")
            return
        kwargs = {"cmap": spec.get("cmap") or "ylgn"}
        if {"west", "south", "east", "north"} <= set(query):
            kwargs.update(
                west=float(query["west"][0]),
                south=float(query["south"][0]),
                east=float(query["east"][0]),
                north=float(query["north"][0]),
            )
        if query.get("size"):
            kwargs["max_side"] = int(query["size"][0])
        if query.get("vmin") and query.get("vmax"):
            kwargs["vmin"] = float(query["vmin"][0])
            kwargs["vmax"] = float(query["vmax"][0])
        try:
            data = overlay_png(resolve_raster(spec["file"]), **kwargs)
        except Exception as exc:
            self._send_error(400, str(exc))
            return
        self._send_bytes(data, "image/png")

    def _send_basemap(self, path: str) -> None:
        try:
            _, z, x, name = path.strip("/").split("/")
            y = int(name.replace(".png", ""))
            z_i, x_i = int(z), int(x)
        except ValueError:
            self._send_error(400, "Tile khong hop le")
            return
        cache = TILE_CACHE / z / x / f"{y}.png"
        if cache.exists():
            self._send_bytes(cache.read_bytes(), "image/png")
            return
        for template in BASEMAP_SOURCES:
            url = template.format(z=z_i, x=x_i, y=y)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "DeepLiDARPlanet-local-viewer/1.0"},
            )
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = resp.read()
                if data[:4] == b"\x89PNG" or data[:2] == b"\xff\xd8":
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_bytes(data)
                    self._send_bytes(data, "image/png")
                    return
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
        fallback = STATIC_DIR / "vendor" / "empty-tile.png"
        if fallback.exists():
            self._send_bytes(fallback.read_bytes(), "image/png")
            return
        self._send_error(502, "Khong tai duoc nen ban do")

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", cache=False)

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        path = path.resolve()
        allowed = (STATIC_DIR.resolve(), get_output_dir().resolve(), get_data_dir().resolve())
        if not path.exists() or not path.is_file() or not any(_is_relative_to(path, root) for root in allowed):
            self._send_error(404, "File not found")
            return
        guessed, _ = mimetypes.guess_type(str(path))
        if path.suffix.lower() in {".tif", ".tiff"}:
            guessed = "image/tiff"
        cache = path.suffix.lower() not in {".html", ".js", ".css"}
        self._send_bytes(path.read_bytes(), content_type or guessed or "application/octet-stream", cache=cache)

    def _send_bytes(self, data: bytes, content_type: str, cache: bool = True) -> None:
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=60" if cache else "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return

    def _send_error(self, code: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class ViewerServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def _local_url() -> str:
    return f"http://127.0.0.1:{PORT}/"


def _server_responds() -> bool:
    try:
        req = urllib.request.Request(
            _local_url(),
            headers={"User-Agent": "AGB-UAV-launcher"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return 200 <= getattr(resp, "status", 200) < 500
    except Exception:
        return False


def _pids_listening_on_port(port: int) -> list[int]:
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return []
    pids: list[int] = []
    me = os.getpid()
    port_s = str(port)
    for line in (completed.stdout or "").splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        _host, sep, local_port = parts[1].rpartition(":")
        if not sep or local_port != port_s:
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid and pid != me and pid not in pids:
            pids.append(pid)
    return pids


def _stop_pids(pids: list[int]) -> None:
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
        )


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    if not STATIC_DIR.exists():
        raise SystemExit(f"Missing static folder: {STATIC_DIR}")
    local_url = _local_url()
    lan_url = f"http://{local_ip()}:{PORT}/"

    if _server_responds():
        print(f"Server da dang chay tai: {local_url}")
        print(f"IP local (LAN):          {lan_url}")
        _open_browser(local_url)
        print("Giu cua so nay mo. Ctrl+C de dong cua so (server cu van chay).")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            print("\nStopped")
        return

    stale = _pids_listening_on_port(PORT)
    if stale:
        print(f"Dang dong tien trinh cu: {stale}")
        _stop_pids(stale)
        time.sleep(0.6)

    try:
        server = ViewerServer((HOST, PORT), ViewerHandler)
    except OSError as exc:
        print(f"Khong mo duoc cong {PORT}: {exc}", file=sys.stderr)
        print(f"Thu dong ung dung dang dung {local_url}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Xem GeoTIFF (rasterio) tai: {local_url}")
    print(f"IP local (LAN):             {lan_url}")
    print(f"Thu muc output: {get_output_dir()}")
    print("Giu cua so nay mo khi dung viewer. Ctrl+C de dung.")
    _open_browser(local_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
        server.server_close()


if __name__ == "__main__":
    main()
