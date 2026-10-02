import ee, os, datetime, geemap, traceback
import geopandas as gpd
from flask import request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta 
import numpy as np
from pathlib import Path


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

def chi2cdf(chi2, df):
    """Calculates Chi square cumulative distribution function for
       df degrees of freedom using the built-in incomplete gamma
       function gammainc().
    """
    return ee.Image(chi2.divide(2)).gammainc(ee.Number(df).divide(2))

def det(im):
    """Calculates determinant of 2x2 diagonal covariance matrix."""
    return im.expression('b(0)*b(1)')

def get_commune_roi(province, district):
    """Return (ee.Geometry, error_message). Accepts comma-separated district names."""
    shapefile_path = resolve_commune_shapefile(province)
    if not shapefile_path.exists():
        return None, f"Không tìm thấy shapefile {shapefile_path}"

    gdf = gpd.read_file(shapefile_path)
    gdf['tenxa_norm'] = gdf['tenxa'].astype(str).str.lower().str.strip()

    if district and str(district).strip():
        # Accept CSV or list
        if isinstance(district, str) and ',' in district:
            parts = [d.strip().lower() for d in district.split(',') if d.strip()]
        elif isinstance(district, (list, tuple)):
            parts = [str(d).strip().lower() for d in district if str(d).strip()]
        else:
            parts = [str(district).strip().lower()]

        if not parts:
            return None, 'Empty district selection'

        gdf = gdf[gdf['tenxa_norm'].isin(parts)]
        if gdf.empty:
            return None, f'Không tìm thấy xã/phường "{district}" trong {province}'

    union_geom = gdf.unary_union
    if union_geom.is_empty:
        return None, f'Không tìm thấy hình học hợp lệ cho xã/phường "{district}" trong {province}'
    if not union_geom.is_valid:
        union_geom = union_geom.buffer(0)
    geom = union_geom.__geo_interface__
    return ee.Geometry(geom), None


def get_commune_gdf(province, district):
    shapefile_path = resolve_commune_shapefile(province)
    if not shapefile_path.exists():
        return None, f"Không tìm thấy shapefile {shapefile_path}"

    gdf = gpd.read_file(shapefile_path)
    if "tenxa" not in gdf.columns:
        return None, "Shapefile không có cột tenxa"

    if district and str(district).strip():
        gdf["tenxa_norm"] = gdf["tenxa"].astype(str).str.lower().str.strip()
        district_norms = [part.strip().lower() for part in str(district).split(",") if part.strip()]
        gdf = gdf[gdf["tenxa_norm"].isin(district_norms)]
        if gdf.empty:
            return None, f'Không tìm thấy xã/phường "{district}" trong {province}'

    return gdf, None

def omnibus(im_list, m = 4.4):
    """Calculates the omnibus test statistic, monovariate case."""
    def log(current):
        return ee.Image(current).log()

    im_list = ee.List(im_list)
    k = im_list.length()
    klogk = k.multiply(k.log())
    klogk = ee.Image.constant(klogk)
    sumlogs = ee.ImageCollection(im_list.map(log)).reduce(ee.Reducer.sum())
    logsum = ee.ImageCollection(im_list).reduce(ee.Reducer.sum()).log()
    return klogk.add(sumlogs).subtract(logsum.multiply(k)).multiply(-2*m)

def selectvv(current):
    return ee.Image(current).select('VV')


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
    # Try string format first for compatibility, then dict
    try:
        return feature_collection.getDownloadURL('geojson')
    except Exception:
        try:
            return feature_collection.getDownloadURL({'format': 'geojson'})
        except Exception as e:
            print('vector download error:', str(e))
            return None


def forerest_detect():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    GLC10 = ee.ImageCollection("projects/sat-io/open-datasets/FROM-GLC10")
    mosaic = GLC10.mosaic().remap([10,20,30,40,60,80,90],[0,1,0,0,0,0,0])
    lulc_remap = mosaic.gt(0)

        
    # === Xác định vùng ROI ===
    gdf, gdf_error = get_commune_gdf(province, district)
    if gdf_error:
        return jsonify({'error': gdf_error}), 404

    roi, roi_error = get_commune_roi(province, district)
    if roi_error:
        return jsonify({'error': roi_error}), 404

    if roi is None:
        return jsonify({'error': 'Không xác định được vùng ROI'}), 404

    scale = 10 if district else 30


    # === Lọc dữ liệu Sentinel-1 ===
    im_coll = (ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(roi)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
        .filter(ee.Filter.eq("resolution_meters", 10))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .map(lambda img: img.clip(roi))
        .sort("system:time_start")
    )

    def clip_img(img):
        return ee.Image(img).clip(roi)

    im_list = im_coll.toList(im_coll.size())
    im_list = ee.List(im_list.map(clip_img))

    vv_list = im_list.map(selectvv)

    
    # === Phát hiện biến động ===
    k = 15
    alpha = 0.5
    p_value = ee.Image.constant(1).subtract(chi2cdf(omnibus(vv_list), k - 1))
    c_map = p_value.multiply(0).where(p_value.lt(1 - (1 - alpha) ** 25), 1)
    c_map = c_map.updateMask(c_map.gt(0))
    mosaic_selected = lulc_remap.clip(roi)
    c_map = c_map.updateMask(mosaic_selected)    

    # ==========================================
    # Tìm polygon mất rừng lớn nhất
    # ==========================================
    c_map_int = c_map.toInt()
    vectors = c_map_int.selfMask().reduceToVectors(
        geometry=roi,
        scale=scale,
        geometryType='polygon',
        eightConnected=True,
        reducer=ee.Reducer.countEvery(),
        maxPixels=1e13
    )

    def add_area(feature):
        area_ha = (
            feature.geometry()
            .area(maxError=1)
            .divide(10000)
        )
        return feature.set('area_ha', area_ha)

    vectors = vectors.map(add_area)
    vectors = vectors.filter(
        ee.Filter.greaterThan('area_ha', 0.5)
    )
    # add properties to each vector feature for consistency
    vectors = vectors.map(lambda f: f.set({'class': 1, 'label': 'change'}))

    largest_feature = ee.Feature(
        vectors.sort('area_ha', False).first()
    )
    largest_center = None
    largest_area = None

    try:
        largest_center = (
            largest_feature.geometry()
            .centroid(maxError=1)
            .coordinates()
            .getInfo()
        )

        largest_area = (
            largest_feature.get('area_ha')
            .getInfo()
        )

    except Exception as e:
        print("largest_feature error:", str(e))
    # === Visualization parameters ===
    
    c_map_filtered = (
        vectors
        .reduceToImage(
            properties=['class'],
            reducer=ee.Reducer.first()
        )
        .selfMask()
    )
    # === Tính diện tích (value = 1) ===
    area_ha_value = ee.Number(
        vectors.aggregate_sum('area_ha')
    ).getInfo()

    area_ha_by_commune = None
    if gdf is not None:
        commune_gdf = gdf.loc[gdf.geometry.notna()].copy()
        commune_gdf['tenxa_norm'] = commune_gdf['tenxa'].astype(str).str.lower().str.strip()
        commune_gdf = commune_gdf.dissolve(by='tenxa_norm', as_index=False, aggfunc={'tenxa': 'first'})

        commune_features = []
        for _, row in commune_gdf.iterrows():
            if row.geometry is None or row.geometry.is_empty:
                continue
            commune_features.append(
                ee.Feature(
                    ee.Geometry(row.geometry.__geo_interface__),
                    {'tenxa': row['tenxa']}
                )
            )

        if commune_features:
            commune_fc = ee.FeatureCollection(commune_features)
            commune_area_fc = c_map_filtered.reduceRegions(
                collection=commune_fc,
                reducer=ee.Reducer.sum(),
                scale=scale
            )

            commune_area_info = commune_area_fc.getInfo()
            area_ha_by_commune = []
            for feature in commune_area_info.get('features', []):
                props = feature.get('properties', {})
                area_m2_commune = props.get('sum') or 0
                area_ha_by_commune.append({
                    'tenxa': props.get('tenxa'),
                    'area_ha': round(area_m2_commune / 10000, 4)
                })

            area_ha_by_commune.sort(key=lambda item: item['area_ha'], reverse=True)

    # === Tạo tile URL để hiển thị ===
    vis_params = {"min": 0, "max": 1, "palette": ['green', 'red']}
    map_dict = c_map_filtered.getMapId(vis_params)
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    # Prefer providing a vector (GeoJSON) download URL for detected polygons
    vector_download = None
    try:
        vector_download = build_vector_download_url(vectors)
    except Exception as e:
        print('vector download build error:', str(e))

    # fallback to raster if vector URL not available
    download_url = vector_download or build_download_url(c_map, roi, scale)

    return jsonify({
        'tile_url': tile_url,
        'download_url': download_url,
        'vector_download_url': vector_download,
        'area_ha': area_ha_value,
        'area_ha_by_commune': area_ha_by_commune,
        'largest_patch': {
            'center': largest_center,
            'area_ha': largest_area
        }
    })

  
