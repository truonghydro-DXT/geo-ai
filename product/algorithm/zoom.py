from flask import Flask, request, jsonify
import geopandas as gpd
import os

def province_bounds():
    province = request.args.get("provinceSelect")
    if not province:
        return jsonify({"error": "Thiếu tên tỉnh"}), 400

    shapefile_path = f"product/commune/hcxa2025_{province}.shp"

    if not os.path.exists(shapefile_path):
        return jsonify({"error": f"Không tìm thấy shapefile: {shapefile_path}"}), 404

    gdf = gpd.read_file(shapefile_path)
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    bbox = {
        "minx": bounds[0],
        "miny": bounds[1],
        "maxx": bounds[2],
        "maxy": bounds[3]
    }
    return jsonify({"bbox": bbox})
