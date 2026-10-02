import ee, os, datetime, geemap, traceback
import geopandas as gpd
from flask import request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta 

def get_sentinel2_image(start, end, region):
    """Trả về ee.Image đã mask cloud và clip theo shapefile."""
    bandS2 = ['B2','B3','B4','B5','B8', 'B8A', 'B9', 'B11','B12']
    
    s2Sr = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').select(bandS2)
    s2Clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')

    criteria = ee.Filter.And(
        ee.Filter.bounds(region),
        ee.Filter.date(start, end)
    )

    s2Sr = s2Sr.filter(criteria)
    s2Clouds = s2Clouds.filter(criteria)

    def maskClouds(img):
        clouds = ee.Image(img.get('cloud_mask')).select('probability')
        return img.updateMask(clouds.lt(30))

    condition = ee.Filter.equals(leftField='system:index', rightField='system:index')
    s2WithCloudMask = ee.Join.saveFirst('cloud_mask').apply(
        primary=s2Sr,
        secondary=s2Clouds,
        condition=condition
    )

    return ee.ImageCollection(s2WithCloudMask).map(maskClouds).mosaic().clip(region)

def get_sentinel2_value(start, end, shapefile_path):
    bandS2 = ['B2','B3','B4','B5','B8', 'B8A', 'B9', 'B11','B12']
    
    s2Sr = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').select(bandS2)
    s2Clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')

    criteria = ee.Filter.And(
        ee.Filter.bounds(shapefile_path),
        ee.Filter.date(start, end)
    )

    s2Sr = s2Sr.filter(criteria)
    s2Clouds = s2Clouds.filter(criteria)

    condition = ee.Filter.equals(leftField='system:index', rightField='system:index')
    joined = ee.Join.saveFirst('cloud_mask').apply(s2Sr, s2Clouds, condition)

    def maskClouds(img):
        cloud = ee.Image(img.get('cloud_mask'))
        return img.updateMask(cloud.select('probability').lt(30))

    return ee.ImageCollection(joined).map(maskClouds)

def get_commune_roi(province, district):
    """Return an ee.Geometry for a single district or a CSV/list of districts.

    `district` may be a single name or a comma-separated string of names.
    Raises ValueError if no matching commune is found.
    """
    shapefile_path = f"public/commune/hcxa2025_{province}.shp"
    if not os.path.exists(shapefile_path):
        raise ValueError(f"Shapefile not found: {shapefile_path}")

    gdf = gpd.read_file(shapefile_path)
    # normalize commune name column
    gdf['tenxa_norm'] = gdf['tenxa'].astype(str).str.lower().str.strip()

    if not district:
        # whole province
        union_geom = gdf.unary_union
    else:
        # accept CSV or list-like strings
        if isinstance(district, str) and ',' in district:
            parts = [d.strip().lower() for d in district.split(',') if d.strip()]
        elif isinstance(district, (list, tuple)):
            parts = [str(d).strip().lower() for d in district if str(d).strip()]
        else:
            parts = [str(district).strip().lower()]

        if not parts:
            raise ValueError('Empty district selection')

        gdf_filtered = gdf[gdf['tenxa_norm'].isin(parts)]
        if gdf_filtered.empty:
            raise ValueError(f'Không tìm thấy xã/phường "{district}" trong {province}')

        union_geom = gdf_filtered.unary_union

    # Ensure geometry validity
    try:
        if not union_geom.is_valid:
            union_geom = union_geom.buffer(0)
    except Exception:
        # best-effort: try buffering
        union_geom = union_geom.buffer(0)

    geom = union_geom.__geo_interface__
    return ee.Geometry(geom)

def sentinel2_api():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    try:
        if not district:
            shapefile_path = f"public/commune/hcxa2025_{province}.shp"
            if not os.path.exists(shapefile_path):
                return jsonify({'error': f'Shapefile not found: {shapefile_path}'}), 404
            gdf = gpd.read_file(shapefile_path)
            union_geom = gdf.unary_union
            roi = ee.Geometry(union_geom.__geo_interface__)
        else:
            roi = get_commune_roi(province, district)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': 'Lỗi khi xây dựng vùng quan tâm: ' + str(e)}), 500
   
    img = get_sentinel2_image(start, end, roi)

    vis_params = {
        "bands": ['B4', 'B3', 'B2'],
        "min": 0,
        "max": 3000,
        "gamma": 1.5
    }

    map_dict = img.getMapId(vis_params)

    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({'tile_url': tile_url})

def get_sentinel1_image(start, end, roi):
    """Trả về ee.Image Sentinel-1 đã composite và clip theo shapefile."""
    

    # Load Sentinel-1 GRD
    s1 = ee.ImageCollection('COPERNICUS/S1_GRD') \
        .filterBounds(roi) \
        .filterDate(start, end) \
        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))

    # ASC & DESC
    asc = s1.filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING'))
    desc = s1.filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))

    # Composite: tạo image 3 kênh
    S1_composite = ee.Image.cat([
        asc.select('VH').mean(),
        ee.ImageCollection(asc.select('VV').merge(desc.select('VV'))).mean(),
        desc.select('VH').mean()
    ]).focal_median()

    # Clip theo ROI
    return S1_composite.clip(roi)


def sentinel1_api():
    """API route trả về tile_url Sentinel-1"""
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    if not district:
        shapefile_path = f"public/commune/hcxa2025_{province}.shp"
        gdf = gpd.read_file(shapefile_path)
        union_geom = gdf.union_all()
        geom = union_geom.__geo_interface__
        roi = ee.Geometry(geom)
    else :
        roi = get_commune_roi(province, district)
   
    img = get_sentinel1_image(start, end, roi)

    vis_params = {
        'min': [-25, -20, -25],
        'max': [0, 10, 0],
        'bands': ['VH', 'VV', 'VH']
    }

    map_dict = img.getMapId(vis_params)

    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({'tile_url': tile_url})


def planet_api():
    try:
        end = request.args.get("end")

        if not end:
            return jsonify({"error": "Thiếu tham số end"}), 400

        end_date = datetime.strptime(end, "%Y-%m-%d")

        # === Kiểm tra nếu end cùng tháng-năm với thời gian hiện tại thì tự lùi lại 1 tháng ===
        today = datetime.today()
        if end_date.year == today.year and end_date.month == today.month:
            end_date = end_date - relativedelta(months=1)

        year = end_date.year
        month = str(end_date.month).zfill(2)
    
        api_key = "PLAK35a4e85d180f4d53a14760706a5cd264"
        tile_url = (
            f"https://tiles.planet.com/basemaps/v1/planet-tiles/"
            f"global_monthly_{year}_{month}_mosaic/gmap/{{z}}/{{x}}/{{y}}.png?api_key={api_key}"
        )

        return jsonify({
            "tile_url": tile_url,
            "year": year,
            "month": month
        })

    except Exception as e:
        import traceback
        print("🔥 Lỗi Planet API:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500