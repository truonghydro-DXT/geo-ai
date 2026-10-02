import math
import threading
from datetime import datetime, timedelta
from pathlib import Path

import ee
import geopandas as gpd
from flask import jsonify, request
from shapely.geometry import mapping


MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_START = "2023-03-01"
DEFAULT_END = "2023-03-31"
DEFAULT_CRS = "EPSG:32648"
PREDICTOR_BANDS = [
    "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B11", "B12",
    "VV_iqr", "VH_iqr", "elevation", "slope", "Map",
]
AGB_PALETTE = [
    "#ffffe5", "#f7fcb9", "#d9f0a3", "#addd8e", "#78c679",
    "#41ab5d", "#238443", "#006837", "#004529",
]
# IPCC 2006/2019 AFOLU: carbon fraction of aboveground biomass (dry matter).
IPCC_CARBON_FRACTION = 0.47
AGB_SCALE_M = 30
# Predicted raster is Mg/ha; Earth Engine sum is Σ(Mg/ha) over 30 m pixels.
PIXEL_AREA_HA = (AGB_SCALE_M * AGB_SCALE_M) / 10_000.0
MEAN_AGB_UNIT = "Mg/ha"
STOCK_UNIT = "10^3 tấn"

_AGB_LOCK = threading.Lock()
_AGB_CACHE = {"key": None, "image": None}


def _stock_thousand_tons(density_sum_mg_ha: float) -> float:
    total_tons = float(density_sum_mg_ha or 0) * PIXEL_AREA_HA
    return round(total_tons / 1000.0, 4)


def _resolve_shapefile(province):
    candidates = [
        MODULE_DIR.parent / "commune" / f"hcxa2025_{province}.shp",
        MODULE_DIR.parent.parent / "public" / "commune" / f"hcxa2025_{province}.shp",
        MODULE_DIR.parent.parent / "product" / "commune" / f"hcxa2025_{province}.shp",
    ]
    for shapefile_path in candidates:
        if shapefile_path.exists():
            return shapefile_path
    return candidates[0]


def _get_commune_gdf(province, district):
    shapefile_path = _resolve_shapefile(province)
    if not shapefile_path.exists():
        return None, f"Không tìm thấy shapefile {shapefile_path}"

    gdf = gpd.read_file(shapefile_path)
    if "tenxa" not in gdf.columns:
        return None, "Shapefile không có cột tenxa"
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    gdf["tenxa_norm"] = gdf["tenxa"].astype(str).str.lower().str.strip()
    if district and str(district).strip():
        names = {item.strip().lower() for item in str(district).split(",") if item.strip()}
        gdf = gdf[gdf["tenxa_norm"].isin(names)]
        if gdf.empty:
            return None, f'Không tìm thấy xã/phường "{district}" trong {province}'
    return gdf, None


def _get_roi(gdf):
    geometry = gdf.geometry.dropna().union_all()
    if geometry.is_empty:
        return None
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    return ee.Geometry(mapping(geometry))


def _mask_s2_clouds(image):
    qa = image.select("QA60")
    cloud_mask = ee.Number(2).pow(10).int()
    cirrus_mask = ee.Number(2).pow(11).int()
    mask = qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
    return image.updateMask(mask).divide(10000)


def _safe_s2_composite(collection, roi):
    bands = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B11", "B12"]
    fallback = ee.Image.constant([0] * len(bands)).rename(bands)
    composite = ee.Image(ee.Algorithms.If(
        collection.size().gt(0),
        collection.map(_mask_s2_clouds).median().clip(roi),
        fallback.clip(roi),
    ))
    return composite.unmask(0).reproject(crs=DEFAULT_CRS, scale=30)


def _safe_s1_features(collection, roi):
    bands = ["VV_p50", "VH_p50", "VV_iqr", "VH_iqr"]
    fallback = ee.Image.constant([0] * len(bands)).rename(bands)
    percentiles = collection.reduce(ee.Reducer.percentile([25, 50, 75]))
    linear = ee.Image(10).pow(percentiles.divide(10))
    features = linear.select(["VV_p50", "VH_p50"])
    features = features.addBands(
        linear.select("VV_p75").subtract(linear.select("VV_p25")).rename("VV_iqr")
    )
    features = features.addBands(
        linear.select("VH_p75").subtract(linear.select("VH_p25")).rename("VH_iqr")
    )
    return ee.Image(ee.Algorithms.If(collection.size().gt(0), features, fallback)).unmask(0).clip(roi).reproject(
        crs=DEFAULT_CRS, scale=30
    )


def _map_url(image, vis_params):
    map_dict = image.getMapId(vis_params)
    if "tile_fetcher" in map_dict:
        return map_dict["tile_fetcher"].url_format
    if "mapid" in map_dict and "token" in map_dict:
        return (
            "https://earthengine.googleapis.com/v1alpha/projects/"
            f"earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
        )
    return None


def _download_url(image, roi, scale):
    try:
        return image.getDownloadURL({
            "name": "AGBD_GEDI_2023",
            "region": ee.Geometry(roi).bounds(maxError=1000),
            "scale": scale,
            "crs": DEFAULT_CRS,
            "format": "GEO_TIFF",
        })
    except Exception as exc:
        print("AGB download URL error:", exc)
        return None


def _rmse(sample):
    try:
        values = sample.reduceColumns(ee.Reducer.toList(2), ["AGB", "predicted"]).get("list").getInfo()
        if not values:
            return None
        return math.sqrt(sum((float(row[0]) - float(row[1])) ** 2 for row in values) / len(values))
    except Exception as exc:
        print("AGB RMSE error:", exc)
        return None


def _commune_stats(regression, gdf):
    features = [
        ee.Feature(ee.Geometry(mapping(row.geometry)), {"tenxa": row["tenxa"]})
        for _, row in gdf.iterrows()
        if row.geometry is not None and not row.geometry.is_empty
    ]
    if not features:
        return []
    result = regression.reduceRegions(
        collection=ee.FeatureCollection(features),
        reducer=ee.Reducer.mean().combine(ee.Reducer.sum(), sharedInputs=True),
        scale=AGB_SCALE_M,
    ).getInfo()
    values = []
    for item in result.get("features", []):
        properties = item.get("properties", {})
        total_agb = _stock_thousand_tons(properties.get("sum") or 0)
        values.append({
            "tenxa": properties.get("tenxa"),
            "mean_agb": round(float(properties.get("mean") or 0), 4),
            "total_agb": total_agb,
            "total_carbon": round(total_agb * IPCC_CARBON_FRACTION, 4),
        })
    return sorted(values, key=lambda item: item["mean_agb"], reverse=True)


def _agb_cache_key(province, district, end_date):
    return (str(province or ""), str(district or ""), str(end_date or ""))


def _parse_period(end_date):
    try:
        start_date = (
            datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=45)
        ).strftime("%Y-%m-%d")
    except ValueError:
        return None, f"Ngày kết thúc không hợp lệ: {end_date}"
    return start_date, None


def _parse_polygon_ring(coordinates):
    if not isinstance(coordinates, list):
        raise ValueError("Thiếu tọa độ polygon")
    if len(coordinates) > 500:
        raise ValueError("Polygon quá nhiều đỉnh")
    ring = []
    for item in coordinates:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            lon, lat = float(item[0]), float(item[1])
        elif isinstance(item, dict):
            lon = float(item.get("lon", item.get("lng")))
            lat = float(item.get("lat"))
        else:
            raise ValueError("Tọa độ polygon không hợp lệ")
        if not math.isfinite(lon) or not math.isfinite(lat):
            raise ValueError("Tọa độ polygon không hợp lệ")
        if ring and abs(ring[-1][0] - lon) < 1e-12 and abs(ring[-1][1] - lat) < 1e-12:
            continue
        ring.append((lon, lat))
    if len(ring) < 3:
        raise ValueError("Polygon cần ít nhất 3 đỉnh")
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    if len(ring) < 4:
        raise ValueError("Polygon cần ít nhất 3 đỉnh")
    return ring


def _build_agb_image(roi, start_date, end_date):
    s1 = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterDate(start_date, end_date)
        .filterBounds(roi)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
    )
    s1_features = _safe_s1_features(s1, roi)

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
        .filterDate(start_date, end_date)
        .filterBounds(roi)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .select(["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B11", "B12", "QA60"])
    )
    s2_composite = _safe_s2_composite(s2, roi)

    elevation = ee.Image("USGS/SRTMGL1_003").select("elevation").clip(roi)
    slope = ee.Terrain.slope(elevation).rename("slope")
    forest_mask = ee.ImageCollection("ESA/WorldCover/v100").first().select("Map").eq(10).rename("Map").clip(roi)
    predictors = s2_composite.addBands(s1_features).addBands(elevation).addBands(slope).addBands(forest_mask)

    agb_image = ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB").first().select("AGB").clip(roi)
    points = agb_image.sample(region=roi, scale=100, numPixels=1000, geometries=True).randomColumn("random", 27)
    training_points = points.filter(ee.Filter.lt("random", 0.7))
    training = predictors.select(PREDICTOR_BANDS).sampleRegions(
        collection=training_points, properties=["AGB"], scale=300
    )
    classifier = ee.Classifier.smileRandomForest(50).setOutputMode("REGRESSION").train(
        features=training, classProperty="AGB", inputProperties=PREDICTOR_BANDS
    )
    regression = (
        predictors.select(PREDICTOR_BANDS)
        .classify(classifier, "predicted")
        .updateMask(forest_mask)
        .clip(roi)
    )
    return regression, points, classifier


def _get_agb_image(province, district, end_date, roi, start_date):
    key = _agb_cache_key(province, district, end_date)
    with _AGB_LOCK:
        if _AGB_CACHE["key"] == key and _AGB_CACHE["image"] is not None:
            return _AGB_CACHE["image"]
    image, _points, _classifier = _build_agb_image(roi, start_date, end_date)
    with _AGB_LOCK:
        _AGB_CACHE["key"] = key
        _AGB_CACHE["image"] = image
    return image


def _stat_value(payload, *names):
    for name in names:
        value = payload.get(name)
        if value is not None:
            return float(value)
    return 0.0


def forerest_agb():
    try:
        province = request.args.get("provinceSelect") or "tinhnghean"
        district = request.args.get("districtSelect")
        end_date = request.args.get("end", DEFAULT_END)
        start_date, period_error = _parse_period(end_date)
        if period_error:
            return jsonify({"error": period_error}), 400

        gdf, error = _get_commune_gdf(province, district)
        if error:
            return jsonify({"error": error}), 404
        roi = _get_roi(gdf)
        if roi is None:
            return jsonify({"error": "Không xác định được vùng AOI phù hợp"}), 404

        regression, sampled_points, classifier = _build_agb_image(roi, start_date, end_date)
        with _AGB_LOCK:
            _AGB_CACHE["key"] = _agb_cache_key(province, district, end_date)
            _AGB_CACHE["image"] = regression

        training_points = sampled_points.filter(ee.Filter.lt("random", 0.7))
        validation_points = sampled_points.filter(ee.Filter.gte("random", 0.7))

        training_predictions = regression.sampleRegions(collection=training_points, properties=["AGB"], scale=30)
        validation_predictions = regression.sampleRegions(collection=validation_points, properties=["AGB"], scale=30)
        min_max = regression.reduceRegion(
            reducer=ee.Reducer.minMax(), geometry=roi, scale=30, crs=DEFAULT_CRS,
            bestEffort=True, tileScale=5,
        ).getInfo()
        total_result = regression.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=roi, scale=30, crs=DEFAULT_CRS,
            bestEffort=True, tileScale=5,
        ).getInfo()
        minimum = float(min_max.get("predicted_min", 0) or 0)
        maximum = float(min_max.get("predicted_max", 0) or 0)
        total_agb = _stock_thousand_tons(total_result.get("predicted", 0) or 0)
        importance = classifier.explain().getInfo().get("importance", {})

        return jsonify({
            "province": province,
            "district": district,
            "period": {"start": start_date, "end": end_date},
            "bands": PREDICTOR_BANDS,
            "tile_url": _map_url(regression, {"palette": AGB_PALETTE, "min": minimum, "max": maximum}),
            "download_url": _download_url(regression, roi, 30),
            "vector_download_url": None,
            "min": minimum,
            "max": maximum,
            "mean_agb_unit": MEAN_AGB_UNIT,
            "stock_unit": STOCK_UNIT,
            "total_agb": total_agb,
            "ipcc_carbon_fraction": IPCC_CARBON_FRACTION,
            "total_carbon": round(total_agb * IPCC_CARBON_FRACTION, 4),
            "training_rmse": _rmse(training_predictions),
            "validation_rmse": _rmse(validation_predictions),
            "variable_importance": importance,
            "mean_agb_by_commune": _commune_stats(regression, gdf),
            "palette": AGB_PALETTE,
        })
    except Exception as exc:
        print("AGB error:", exc)
        return jsonify({"error": str(exc)}), 500


def forerest_agb_polygon():
    try:
        payload = request.get_json(silent=True) or {}
        province = payload.get("provinceSelect") or request.args.get("provinceSelect") or "tinhnghean"
        district = payload.get("districtSelect") or request.args.get("districtSelect")
        end_date = payload.get("end") or request.args.get("end") or DEFAULT_END
        try:
            ring = _parse_polygon_ring(payload.get("coordinates") or payload.get("polygon"))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        start_date, period_error = _parse_period(end_date)
        if period_error:
            return jsonify({"error": period_error}), 400

        gdf, error = _get_commune_gdf(province, district)
        if error:
            return jsonify({"error": error}), 404
        roi = _get_roi(gdf)
        if roi is None:
            return jsonify({"error": "Không xác định được vùng AOI phù hợp"}), 404

        regression = _get_agb_image(province, district, end_date, roi, start_date)
        geom = ee.Geometry.Polygon([[list(point) for point in ring]])
        stats = regression.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.sum(), sharedInputs=True),
            geometry=geom,
            scale=AGB_SCALE_M,
            crs=DEFAULT_CRS,
            bestEffort=True,
            tileScale=5,
        ).getInfo() or {}
        area_m2 = geom.area(maxError=1).getInfo()
        mean_agb = _stat_value(stats, "predicted_mean", "mean", "predicted")
        density_sum = _stat_value(stats, "predicted_sum", "sum", "predicted")
        total_agb = _stock_thousand_tons(density_sum)
        total_carbon = round(total_agb * IPCC_CARBON_FRACTION, 4)
        area_ha = round(float(area_m2 or 0) / 10_000.0, 4)
        return jsonify({
            "mean_agb": round(mean_agb, 4),
            "total_agb": total_agb,
            "total_carbon": total_carbon,
            "area_ha": area_ha,
            "vertex_count": len(ring) - 1,
            "mean_agb_unit": MEAN_AGB_UNIT,
            "stock_unit": STOCK_UNIT,
            "ipcc_carbon_fraction": IPCC_CARBON_FRACTION,
        })
    except Exception as exc:
        print("AGB polygon error:", exc)
        return jsonify({"error": str(exc)}), 500