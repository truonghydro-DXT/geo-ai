import ee, json
import geopandas as gpd
from flask import request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta 
import numpy as np

# SERVICE_ACCOUNT_JSON = 'gee-service-account.json'

# with open(SERVICE_ACCOUNT_JSON, 'r', encoding='utf8') as f:
#     sa = json.load(f)

# SERVICE_ACCOUNT_EMAIL = sa['client_email']
# KEY_PATH = SERVICE_ACCOUNT_JSON

# credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT_EMAIL, KEY_PATH)
# ee.Initialize(credentials)

# end = '2025-10-30'
# province = 'tpHaiPhong'
# district = ''

# if not district:
#         shapefile_path = f"commune/hcxa2025_{province}.shp"
#         gdf = gpd.read_file(shapefile_path)
#         union_geom = gdf.union_all()
#         geom = union_geom.__geo_interface__
#         region = ee.Geometry(geom)
# else:
#     shapefile_path = f"commune/hcxa2025_{province}.shp"
#     gdf = gpd.read_file(shapefile_path)
#     gdf['tenxa_norm'] = gdf['tenxa'].astype(str).str.lower().str.strip()
#     district_norm = district.lower().strip()
#     gdf_filtered = gdf[gdf['tenxa_norm'] == district_norm]
#     union_geom = gdf_filtered.union_all()
#     if not union_geom.is_valid:
#         union_geom = union_geom.buffer(0)
#     geom = union_geom.__geo_interface__
#     region = ee.Geometry(geom)

def rain_flood(regions, start_time, end_time):
    """
    Tính lượng mưa và nhiệt độ trung bình giai đoạn start_time → end_time.
    - Nếu end_time cách ngày hiện tại ≤ 7 ngày → dùng GFS (NOAA/GFS0P25)
    - Nếu > 7 ngày → dùng ERA5 (ECMWF/ERA5_LAND/DAILY_AGGR)
    """
    import datetime

    lable_pcp = "total_precipitation_mm"

    # --- Bộ dữ liệu ---
    GFS = ee.ImageCollection("NOAA/GFS0P25")                # gần thời gian thực
    ERA5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR") # lịch sử

    # --- Chuyển đổi dữ liệu ---
    def preprocess_gfs(img):
        # precipitation_rate [kg/m²/s] → mm/6h (6 giờ/lần)
        pcp = img.select("precipitation_rate").multiply(86400).rename(lable_pcp)
        return ee.Image.cat(pcp).copyProperties(img, ["system:time_start"])

    def preprocess_era5(img):
        pcp = img.select("total_precipitation_sum").multiply(1000).rename(lable_pcp)
        return ee.Image.cat(pcp).copyProperties(img, ["system:time_start"])

    GFS = GFS.map(preprocess_gfs)
    ERA5 = ERA5.map(preprocess_era5)

    def daily_mean(date):
        start = ee.Date(date)
        end = start.advance(1, "day")
        daily = GFS.filterDate(start, end).mean()
        return daily.set("system:time_start", start.millis())
    

    # --- Xác định ngày ---
    start_date = ee.Date(start_time)
    end_date = ee.Date(end_time)
    today = datetime.datetime.utcnow()
    # Nếu end_time là ee.Date hoặc ee.String -> chuyển về str (Python)
    if isinstance(end_time, ee.Date):
        end_time_str = end_time.format("YYYY-MM-dd").getInfo()
    elif isinstance(end_time, ee.String):
        end_time_str = end_time.getInfo()
    else:
        end_time_str = str(end_time)

    end_dt = datetime.datetime.strptime(end_time_str, "%Y-%m-%d")

    # --- Kiểm tra khoảng cách thời gian ---
    diff_days = (today - end_dt).days

    # --- scale cố định ---
    fixed_scale = 25000

    def reduce_mean_fixed(image, label):
        return image.select(label).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=regions,
            scale=fixed_scale,
            bestEffort=True,
            maxPixels=1e13
        )
    n_days = end_date.difference(start_date, "day")
    dates = ee.List.sequence(0, n_days.subtract(1)).map(lambda d: start_date.advance(d, "day"))

    # --- Áp dụng tính trung bình từng ngày ---
    GFS_daily = ee.ImageCollection(dates.map(daily_mean))

    # --- Chọn bộ dữ liệu theo độ trễ ---
    use_era5 = diff_days > 7
    dataset = ee.ImageCollection(ee.Algorithms.If(use_era5, ERA5, GFS_daily))

    # --- Tính toán lượng mưa & nhiệt độ ---
    col_period = dataset.filterDate(start_date, end_date)
    pcp_map = col_period.select(lable_pcp).sum().clip(regions)

    # --- Trung bình vùng ---
    pcp_now_mean = ee.Number(
        ee.Dictionary(reduce_mean_fixed(pcp_map, lable_pcp)).get(lable_pcp)
    )
 
    # --- Lượng mưa & nhiệt độ lịch sử (ERA5) ---
    year_now = ee.Number(end_date.get("year")).int()
    month_now = ee.Number(end_date.get("month")).int()
    years = ee.List.sequence(2000, year_now)
    list_dayofmonth = ee.List([31,28,31,30,31,30,31,31,30,31,30,31])
    dayofmonth = ee.Number(list_dayofmonth.get(month_now.subtract(1)))

    def per_year_sum(y):
        y = ee.Number(y)
        s = ee.Date.fromYMD(y, month_now, 1)
        e = ee.Date.fromYMD(y, month_now, dayofmonth)
        return ERA5.filterDate(s, e).select(lable_pcp).sum().set("year", y)

    hist_pcp_col = ee.ImageCollection(years.map(per_year_sum))


    hist_pcp_mean = ee.Number(
        ee.Dictionary(reduce_mean_fixed(hist_pcp_col.mean(), lable_pcp)).get(lable_pcp)
    )

    # --- Tỷ lệ ---
    pcp_ratio = ee.Algorithms.If(
        hist_pcp_mean.gt(0),
        pcp_now_mean.divide(hist_pcp_mean).multiply(100),
        0
    )
    pcp_ratio = ee.Number(pcp_ratio)

    # --- ✅ Trả về ---
    return pcp_ratio

# =========================
# 💧 HÀM PHÁT HIỆN NGẬP
# =========================
import os


def _load_commune_gdf(province, district=None):
    shapefile_path = f"public/commune/hcxa2025_{province}.shp"
    if not os.path.exists(shapefile_path):
        return None, f"Shapefile not found: {shapefile_path}"

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


def get_commune_roi(province, district):
    shapefile_path = f"public/commune/hcxa2025_{province}.shp"
    if not os.path.exists(shapefile_path):
        raise ValueError(f"Shapefile not found: {shapefile_path}")

    gdf = gpd.read_file(shapefile_path)
    gdf['tenxa_norm'] = gdf['tenxa'].astype(str).str.lower().str.strip()

    # Support CSV/list
    if isinstance(district, str) and ',' in district:
        parts = [d.strip().lower() for d in district.split(',') if d.strip()]
    elif isinstance(district, (list, tuple)):
        parts = [str(d).strip().lower() for d in district if str(d).strip()]
    else:
        parts = [str(district).strip().lower()]

    if not parts or parts == ['']:
        raise ValueError('Empty district selection')

    gdf_filtered = gdf[gdf['tenxa_norm'].isin(parts)]
    if gdf_filtered.empty:
        raise ValueError(f'Không tìm thấy xã/phường "{district}" trong {province}')

    union_geom = gdf_filtered.unary_union
    if not union_geom.is_valid:
        union_geom = union_geom.buffer(0)
    geom = union_geom.__geo_interface__
    return ee.Geometry(geom)

def flood_area():
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')

    # --- 1️⃣ Xác định vùng phân tích ---
    try:
        gdf, gdf_error = _load_commune_gdf(province, district)
        if gdf_error:
            return jsonify({'error': gdf_error}), 404

        if not district:
            union_geom = gdf.unary_union
            region = ee.Geometry(union_geom.__geo_interface__)
        else:
            region = get_commune_roi(province, district)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': 'Lỗi khi xây dựng vùng quan tâm: ' + str(e)}), 500

    # --- 2️⃣ Thời gian ---
    afterEnd = ee.Date(end)
    beforeEndRain = afterEnd.advance(-7, "day")
    beforeStart = afterEnd.advance(-1, "month")
    afterStart = ee.Date(afterEnd).advance(-1,'month').format('YYYY-MM-dd')
    beforeEnd = ee.Date(afterEnd).advance(-1,'month').format('YYYY-MM-dd')
    beforeStart = ee.Date(beforeEnd).advance(-2,'month').format('YYYY-MM-dd')

    # --- 3️⃣ Kiểm tra mưa ---
    pcp_ratio = rain_flood(
        region, beforeEndRain.format("YYYY-MM-dd"), afterEnd.format("YYYY-MM-dd")
    )

    # Lấy giá trị thực tế của tỉ lệ mưa (pcp_ratio)
    ratio_value = pcp_ratio.getInfo()
    # print(ratio_value)

    # ====== ⚠️ Nếu lượng mưa 30 ngày qua < 150mm => dừng lại, không xử lý tiếp ======
    if ratio_value < 50:
        return jsonify({
            "active": 0,
        })

    # --- 4️⃣ Có mưa đáng kể => phân tích ---
    active = 1
    polarization = "VH"
    pass_direction = "DESCENDING"
    difference_threshold = 1.15

    # ===== 1️⃣ Mặt nước vĩnh cửu =====
    dataset = ee.ImageCollection("ESA/WorldCover/v200").first()
    ESA_LULC = dataset.remap([10, 60], [1, 1]).rename("water").selfMask()
    water_mask = ESA_LULC.clip(region)

    # ===== 2️⃣ Sentinel-1 Collection =====
    collection = (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', polarization))
        .filter(ee.Filter.eq('orbitProperties_pass', pass_direction))
        .filter(ee.Filter.eq('resolution_meters', 10))
        .filterBounds(region)
        .select(['VV', 'VH'])
    )

    def filterSpeckles(img):
        vv = img.select('VV')
        vv_smoothed = vv.focal_median(100, 'circle', 'meters').rename('VV_Filtered')
        return img.addBands(vv_smoothed)

    S1_collection = collection.filterDate(beforeStart, afterEnd).map(filterSpeckles)

    # ====== Phân loại nước ======
    def classifyWater(img):
        vv = img.select('VV_Filtered')
        water = vv.lt(-18).rename('Water')
        water = water.updateMask(water)
        return img.addBands(water)

    Water_collection = S1_collection.map(classifyWater)
    classification = ee.Image(Water_collection.mosaic()).select('Water')
    # Giữ lại phần nằm trong vùng nước lâu năm (ít nhiễu)
    classification = classification.updateMask(water_mask.unmask(1))

    # ===== 4️⃣ Phát hiện ngập lụt =====
    before_collection = collection.select(polarization).filterDate(beforeStart, beforeEnd)
    after_collection = collection.select(polarization).filterDate(afterStart, afterEnd)

    before = before_collection.mosaic().clip(region)
    after = after_collection.mosaic().clip(region)

    smoothing_radius = 50
    before_filtered = before.focal_mean(smoothing_radius, 'circle', 'meters')
    after_filtered = after.focal_mean(smoothing_radius, 'circle', 'meters')

    # ====== Tính ngập ======
    difference = after_filtered.divide(before_filtered)
    difference_binary = difference.gt(difference_threshold)

    swater = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('seasonality')
    swater_mask = swater.gte(10).updateMask(swater.gte(10))

    flooded_mask = difference_binary.where(swater_mask, 0)
    flooded = flooded_mask.updateMask(flooded_mask)

    connections = flooded.connectedPixelCount()
    flooded = flooded.updateMask(connections.gte(8))

    DEM = ee.Image('WWF/HydroSHEDS/03VFDEM')
    slope = ee.Algorithms.Terrain(DEM).select('slope')
    flooded = flooded.updateMask(slope.lt(5))


    # ===== 5️⃣ Tính diện tích ngập =====
    area_image = flooded.multiply(ee.Image.pixelArea())
    area_ha = area_image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=10,
        maxPixels=1e13
    ).getInfo()

    area_ha_value = 0
    if area_ha:
        key = list(area_ha.keys())[0]
        area_ha_value = area_ha[key] / 10000

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
            commune_area_fc = area_image.reduceRegions(
                collection=commune_fc,
                reducer=ee.Reducer.sum(),
                scale=10
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

    # ===== 6️⃣ Visualization =====
    palettes = {
        "Vùng nước vĩnh cửu": ["#0A93EE"],
        "Vùng ngập lụt": ["#008000"]
    }

    water_vis = classification.visualize(min=0, max=150, palette=["#016FFF"])
    water_map = water_vis.getMapId({'min': 0, 'max': 150})

    flood_vis = flooded.visualize(min=0, max=1, palette=palettes["Vùng ngập lụt"])
    flood_map = flood_vis.getMapId({'min': 0, 'max': 1})

    def make_tile_url(map_dict):
        if "tile_fetcher" in map_dict:
            return map_dict["tile_fetcher"].url_format
        elif "mapid" in map_dict and "token" in map_dict:
            return (
                 f"https://earthengine.googleapis.com/map/{map_dict['mapid']}/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
            )
        return None

    water_url = make_tile_url(water_map)
    flood_url = make_tile_url(flood_map)

    # ===== 7️⃣ Trả về JSON =====
    return jsonify({
        "active": active,
        "Permanent Water": {
            "tile_url": water_url,
            "palette": palettes["Vùng nước vĩnh cửu"][0],
            "area_ha": None
        },
        "Flooded Area": {
            "tile_url": flood_url,
            "palette": palettes["Vùng ngập lụt"][0],
            "area_ha": area_ha_value,
            "area_ha_by_commune": area_ha_by_commune
        }
    })
# flood_area()