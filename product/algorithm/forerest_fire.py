import os
from datetime import datetime, timedelta
from pathlib import Path

import ee
import geopandas as gpd
from flask import jsonify, request


MODULE_DIR = Path(__file__).resolve().parent


def resolve_commune_shapefile(province):
    """Resolve commune shapefile for product or public layouts."""
    candidates = [
        MODULE_DIR.parent / "commune" / f"hcxa2025_{province}.shp",
        MODULE_DIR.parent.parent / "public" / "commune" / f"hcxa2025_{province}.shp",
        MODULE_DIR.parent.parent / "product" / "commune" / f"hcxa2025_{province}.shp",
    ]
    for shapefile_path in candidates:
        if shapefile_path.exists():
            return shapefile_path
    return candidates[0]


def _get_roi(province, district):
    shapefile_path = resolve_commune_shapefile(province)
    if not shapefile_path.exists():
        return None

    gdf = gpd.read_file(shapefile_path)
    if district and str(district).strip():
        if "tenxa" not in gdf.columns:
            return None

        gdf["tenxa_norm"] = gdf["tenxa"].astype(str).str.lower().str.strip()
        district_norms = [part.strip() for part in str(district).split(",") if part.strip()]
        district_norms = [item.lower() for item in district_norms]
        gdf = gdf[gdf["tenxa_norm"].isin(district_norms)]
        if gdf.empty:
            return None

    union_geom = gdf.union_all()
    if union_geom.is_empty:
        return None
    if not union_geom.is_valid:
        union_geom = union_geom.buffer(0)

    return ee.Geometry(union_geom.__geo_interface__)


def _get_commune_gdf(province, district):
    shapefile_path = resolve_commune_shapefile(province)
    if not shapefile_path.exists():
        return None

    gdf = gpd.read_file(shapefile_path)
    if district and str(district).strip():
        if "tenxa" not in gdf.columns:
            return None

        gdf["tenxa_norm"] = gdf["tenxa"].astype(str).str.lower().str.strip()
        district_norms = [part.strip().lower() for part in str(district).split(",") if part.strip()]
        gdf = gdf[gdf["tenxa_norm"].isin(district_norms)]
        if gdf.empty:
            return None

    return gdf


def _calc_nbr(image):
    return image.addBands(image.normalizedDifference(["B8", "B12"]).rename("NBR"))


def _safe_median_nbr(collection):
    fallback = ee.Image.constant(0).rename("NBR")
    return ee.Image(
        ee.Algorithms.If(
            collection.size().gt(0),
            collection.map(_calc_nbr).median(),
            fallback,
        )
    )


def _safe_median_vh(collection):
    fallback = ee.Image.constant(0).rename("VH")
    return ee.Image(
        ee.Algorithms.If(
            collection.size().gt(0),
            collection.select("VH").median(),
            fallback,
        )
    )

def build_download_url(image, roi, scale):
    """Try to build a GeoTIFF download URL with a compact region and fallback scales."""
    download_region = ee.Geometry(roi).bounds(maxError=1000)
    for factor in [1, 2, 4, 8, 16]:
        try:
            return image.getDownloadURL({
                'name': 'forerest_result',
                'region': download_region,
                'scale': scale,
                'format': 'GEO_TIFF'
            })
        except Exception as e:
            print(f'download_url scale x{factor} error:', str(e))
    return None


def build_vector_download_url(feature_collection):
    """Try to build a GeoJSON download URL for a FeatureCollection."""
    # Some EE client versions expect a string format argument; others accept a dict.
    try:
        return feature_collection.getDownloadURL('geojson')
    except Exception:
        try:
            return feature_collection.getDownloadURL({'format': 'geojson'})
        except Exception as e:
            print('vector download error:', str(e))
            return None

def forerest_fire():
    province = request.args.get("provinceSelect") or "tinhdaklak"
    district = request.args.get("districtSelect")
    end_value = request.args.get("end")
    if end_value:
        try:
            post_fire_end_dt = datetime.strptime(end_value, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Định dạng end không hợp lệ, dùng YYYY-MM-DD"}), 400
        post_fire_end = post_fire_end_dt.strftime("%Y-%m-%d")
        post_fire_start = (post_fire_end_dt - timedelta(days=14)).strftime("%Y-%m-%d")
        pre_fire_end = (post_fire_end_dt - timedelta(days=15)).strftime("%Y-%m-%d")
        pre_fire_start = (post_fire_end_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    else:
        pre_fire_start = request.args.get("preFireStart", "2026-03-01")
        pre_fire_end = request.args.get("preFireEnd", "2026-03-30")
        post_fire_start = request.args.get("postFireStart", "2026-04-01")
        post_fire_end = request.args.get("postFireEnd", "2026-04-30")

    gdf = _get_commune_gdf(province, district)
    if gdf is None:
        return jsonify({"error": "Không tìm thấy shapefile hoặc xã/phường phù hợp"}), 404

    aoi = _get_roi(province, district)
    scale=10 if district else 100

    if aoi is None:
        return jsonify({"error": "Không tìm thấy vùng AOI phù hợp"}), 404

    pre_s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(pre_fire_start, pre_fire_end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
    )
    post_s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(post_fire_start, post_fire_end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
    )

    pre_s2 = _safe_median_nbr(pre_s2)
    post_s2 = _safe_median_nbr(post_s2)

    glc10 = ee.ImageCollection("projects/sat-io/open-datasets/FROM-GLC10")
    mosaic = glc10.mosaic().remap([10, 20, 30, 40, 60, 80, 90], [0, 0, 1, 1, 1, 0, 0])
    forest_mask = mosaic.gt(0).clip(aoi)

    d_nbr = pre_s2.select("NBR").subtract(post_s2.select("NBR")).rename("dNBR")
    d_nbr = d_nbr.updateMask(forest_mask)

    s1_pre = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(pre_fire_start, pre_fire_end)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select("VH")
    )
    s1_post = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(post_fire_start, post_fire_end)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select("VH")
    )

    pre_s1 = _safe_median_vh(s1_pre)
    post_s1 = _safe_median_vh(s1_post)
    s1_diff = pre_s1.subtract(post_s1).rename("VH_diff")

    classified = ee.Image(1)
    classified = classified.where(d_nbr.gte(-0.1).And(d_nbr.lt(0)), 1)
    classified = classified.where(d_nbr.gte(0).And(d_nbr.lt(0.2)), 2)
    classified = classified.where(d_nbr.gte(0.2).And(d_nbr.lt(0.4)), 3)
    classified = classified.where(d_nbr.gte(0.4).And(d_nbr.lt(0.6)), 4)
    # classified = classified.updateMask(forest_mask)

    # class_values = {
    #     'Nguy cơ thấp': 1,
    #     'Nguy cơ trung bình': 2,
    #     'Nguy cơ cao': 3,
    #     'Nguy cơ rất cao': 4
    # }

    # palettes = {
    #     'Nguy cơ thấp': ["#064696"],
    #     'Nguy cơ trung bình': ["#EAEE0D"],
    #     'Nguy cơ cao': ["#F01919"],
    #     'Nguy cơ rất cao': ["#F70CEB"]
    # }
    
    # # --- Lưu tile URL cho tất cả lớp ---

    # tiles = {}
    # pixel_area = ee.Image.pixelArea().divide(10000)
    # vector_collections = []

    # for name, class_value in class_values.items():
    #     layer = classified.eq(class_value).selfMask().rename('class')
    #     class_area_image = layer.multiply(pixel_area).rename('class')

    #     vis_params = {'palette': palettes[name], 'min': 1, 'max': 1}
    #     map_dict = layer.getMapId(vis_params)
    #     if 'tile_fetcher' in map_dict:
    #         tile_url = map_dict['tile_fetcher'].url_format
    #     elif 'mapid' in map_dict and 'token' in map_dict:
    #         tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    #     else:
    #         tile_url = None

    #     area = class_area_image.reduceRegion(
    #         reducer=ee.Reducer.sum(),
    #         geometry=aoi,
    #         scale=scale,
    #         maxPixels=9e13,
    #         tileScale=4
    #     ).get('class')
    #     area_ha = area.getInfo() if area is not None else 0

    #     area_ha_by_commune = None
    #     if gdf is not None:
    #         if "tenxa" not in gdf.columns:
    #             return jsonify({'error': 'Shapefile không có cột tenxa'}), 500

    #         commune_gdf = gdf.loc[gdf.geometry.notna()].copy()
    #         commune_gdf['tenxa_norm'] = commune_gdf['tenxa'].astype(str).str.lower().str.strip()
    #         commune_gdf = commune_gdf.dissolve(by='tenxa_norm', as_index=False, aggfunc={'tenxa': 'first'})

    #         commune_features = []
    #         for _, row in commune_gdf.iterrows():
    #             if row.geometry is None or row.geometry.is_empty:
    #                 continue
    #             commune_features.append(
    #                 ee.Feature(
    #                     ee.Geometry(row.geometry.__geo_interface__),
    #                     {'tenxa': row['tenxa']}
    #                 )
    #             )

    #         if commune_features:
    #             commune_fc = ee.FeatureCollection(commune_features)
    #             commune_area_fc = class_area_image.reduceRegions(
    #                 collection=commune_fc,
    #                 reducer=ee.Reducer.sum(),
    #                 scale=scale
    #             )

    #             commune_area_info = commune_area_fc.getInfo()
    #             area_ha_by_commune = []
    #             for feature in commune_area_info.get('features', []):
    #                 props = feature.get('properties', {})
    #                 area_m2_commune = props.get('sum') or 0
    #                 area_ha_by_commune.append({
    #                     'tenxa': props.get('tenxa'),
    #                     'area_ha': round(area_m2_commune, 4)
    #                 })

    #             area_ha_by_commune.sort(key=lambda item: item['area_ha'], reverse=True)
    #     # Build a vector FeatureCollection for this class and try to provide a GeoJSON download URL.
    #     mask = classified.eq(class_value).selfMask()
    #     vectors = mask.reduceToVectors(
    #         geometry=aoi,
    #         scale=scale,
    #         geometryType='polygon',
    #         eightConnected=False,
    #         labelProperty='class',
    #         bestEffort=True,
    #         maxPixels=9e13
    #     )
    #     # ensure each feature carries the class value and the risk name
    #     vectors = vectors.map(lambda f: f.set({'class': class_value, 'risk_name': name}))
    #     # collect for combined export
    #     vector_collections.append(vectors)

    #     download_url = build_vector_download_url(vectors)
    #     # Do not call getInfo() on vectors (can be very large >5000 features).
    #     geojson_content = None

    #     # fallback to raster download if vector URL couldn't be built
    #     if download_url is None:
    #         download_url = build_download_url(classified.eq(class_value), aoi, scale)

    #     tiles[name] = {
    #         'tile_url': tile_url,
    #         'download_url': download_url,
    #         'area_ha': area_ha,
    #         'palette': palettes[name],
    #         'area_ha_by_commune': area_ha_by_commune,
    #         'geojson': geojson_content,
    #         'vector_download_url': download_url if download_url and download_url.endswith('.geojson') or (download_url and 'format=geojson' in download_url) else None
    #     }

    # # Combine all class vectors into one FeatureCollection for single-download
    # # Combine all vectors and provide a download URL only (avoid getInfo())
    # all_vectors_download = None
    # try:
    #     if vector_collections:
    #         combined = ee.FeatureCollection(vector_collections).flatten()
    #         all_vectors_download = build_vector_download_url(combined)
    # except Exception as e:
    #     print('combine vectors error:', str(e))

    # response = {
    #     'tiles': tiles,
    #     'all_vectors': {
    #         'vector_download_url': all_vectors_download,
    #         'geojson': None
    #     }
    # }

    classified = classified.updateMask(forest_mask)
    class_values = {
        'Nguy cơ thấp': 1,
        'Nguy cơ trung bình': 2,
        'Nguy cơ cao': 3,
        'Nguy cơ rất cao': 4
    }
    palettes = {
        'Nguy cơ thấp': ["#064696"],
        'Nguy cơ trung bình': ["#EAEE0D"],
        'Nguy cơ cao': ["#F01919"],
        'Nguy cơ rất cao': ["#F70CEB"]
    }

    # ============================================================
    # Lưu tile URL cho tất cả lớp (chỉ vùng > 0.5 ha)
    # ============================================================
    tiles = {}
    vector_collections = []
    pixel_area = ee.Image.pixelArea().divide(10000)
    for name, class_value in class_values.items():
        # --------------------------------------------------------
        # Raster của lớp
        # --------------------------------------------------------
        mask = classified.eq(class_value).selfMask().toByte()
        # --------------------------------------------------------
        # Vector hóa
        # --------------------------------------------------------
        vectors = mask.reduceToVectors(
            geometry=aoi,
            scale=scale,
            geometryType='polygon',
            eightConnected=False,
            reducer=ee.Reducer.countEvery(),
            labelProperty='class',
            bestEffort=True,
            maxPixels=9e13
        )

        # --------------------------------------------------------
        # Tính diện tích từng polygon (ha)
        # --------------------------------------------------------
        def add_area(feature):
            area_ha = (
                feature.geometry()
                .area(maxError=1)
                .divide(10000)
            )
            return feature.set({
                'area_ha': area_ha,
                'class': class_value,
                'risk_name': name
            })
        vectors = vectors.map(add_area)

        # --------------------------------------------------------
        # Chỉ giữ polygon > 0.5 ha
        # --------------------------------------------------------
        vectors = vectors.filter(
            ee.Filter.gt('area_ha', 0.5)
        )

        # --------------------------------------------------------
        # Raster hóa lại để tile chỉ hiển thị >0.5ha
        # --------------------------------------------------------
        layer = (
            vectors
            .reduceToImage(
                properties=['class'],
                reducer=ee.Reducer.first()
            )
            .selfMask()
        )

        # --------------------------------------------------------
        # Tile URL
        # --------------------------------------------------------
        vis_params = {
            'palette': palettes[name],
            'min': 1,
            'max': 1
        }
        map_dict = layer.getMapId(vis_params)
        if 'tile_fetcher' in map_dict:
            tile_url = map_dict['tile_fetcher'].url_format
        elif 'mapid' in map_dict and 'token' in map_dict:
            tile_url = (
                f"https://earthengine.googleapis.com/v1alpha/projects/"
                f"earthengine-legacy/maps/{map_dict['mapid']}"
                f"/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
            )
        else:
            tile_url = None
        # --------------------------------------------------------
        # Tổng diện tích (>0.5ha)
        # --------------------------------------------------------
        try:
            area_ha = (
                ee.Number(
                    vectors.aggregate_sum('area_ha')
                ).getInfo()
            )
        except Exception:
            area_ha = 0
        # --------------------------------------------------------
        # Thống kê theo xã (>0.5ha)
        # --------------------------------------------------------
        area_ha_by_commune = None
        if gdf is not None:
            if "tenxa" not in gdf.columns:
                return jsonify({
                    'error': 'Shapefile không có cột tenxa'
                }), 500
            commune_gdf = gdf.loc[gdf.geometry.notna()].copy()
            commune_gdf['tenxa_norm'] = (
                commune_gdf['tenxa']
                .astype(str)
                .str.lower()
                .str.strip()
            )
            commune_gdf = commune_gdf.dissolve(
                by='tenxa_norm',
                as_index=False,
                aggfunc={'tenxa': 'first'}
            )
            commune_features = []
            for _, row in commune_gdf.iterrows():
                if row.geometry is None:
                    continue
                if row.geometry.is_empty:
                    continue
                commune_features.append(
                    ee.Feature(
                        ee.Geometry(
                            row.geometry.__geo_interface__
                        ),
                        {
                            'tenxa': row['tenxa']
                        }
                    )
                )
            if commune_features:
                commune_fc = ee.FeatureCollection(commune_features)
                area_image = (
                    layer.multiply(
                        ee.Image.pixelArea().divide(10000)
                    )
                )
                commune_area_fc = area_image.reduceRegions(
                    collection=commune_fc,
                    reducer=ee.Reducer.sum(),
                    scale=scale
                )
                commune_area_info = commune_area_fc.getInfo()
                area_ha_by_commune = []
                for feature in commune_area_info.get('features', []):
                    props = feature.get('properties', {})
                    area_ha_commune = props.get('sum') or 0
                    area_ha_by_commune.append({
                        'tenxa': props.get('tenxa'),
                        'area_ha': round(
                            area_ha_commune,
                            4
                        )
                    })
                area_ha_by_commune.sort(
                    key=lambda item: item['area_ha'],
                    reverse=True
                )
        # --------------------------------------------------------
        # Download Vector
        # --------------------------------------------------------
        download_url = build_vector_download_url(vectors)
        if download_url is None:
            download_url = build_download_url(
                layer,
                aoi,
                scale
            )
        vector_collections.append(vectors)
        tiles[name] = {
            'tile_url': tile_url,
            'download_url': download_url,
            'vector_download_url': download_url,
            'geojson': None,
            'area_ha': area_ha,
            'palette': palettes[name],
            'area_ha_by_commune': area_ha_by_commune
        }
    # ============================================================
    # Gộp tất cả vector (>0.5ha)
    # ============================================================
    all_vectors_download = None
    try:
        if vector_collections:
            combined = (
                ee.FeatureCollection(
                    vector_collections
                ).flatten()
            )
            all_vectors_download = (
                build_vector_download_url(
                    combined
                )
            )
    except Exception as e:
        print("combine vectors error:", str(e))
    response = {
        'tiles': tiles,
        'all_vectors': {
            'vector_download_url': all_vectors_download,
            'geojson': None
        }
    }

    return jsonify(response)

   