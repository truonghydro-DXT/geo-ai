import ee, os, datetime, geemap, traceback
import geopandas as gpd
from flask import request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta 
import numpy as np

def get_commune_roi(province, district):
    import os
    shapefile_path = f"public/commune/hcxa2025_{province}.shp"
    if not os.path.exists(shapefile_path):
        raise ValueError(f"Shapefile not found: {shapefile_path}")

    gdf = gpd.read_file(shapefile_path)
    gdf['tenxa_norm'] = gdf['tenxa'].astype(str).str.lower().str.strip()

    # support CSV or list
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

def classify_landuser(roi, enddates):
    # === 1️⃣ Xác định mốc thời gian ===
    startdate_before = ee.Date(enddates).advance(-2, 'month')
    startdate_after = ee.Date(enddates).advance(-1, 'month')
    esri_lulc10 = ee.ImageCollection('projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m')

    # === 2️⃣ Sentinel-2 Surface Reflectance ===
    s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')

    def maskS2clouds(image):
        qa = image.select('SCL')
        mask = qa.And(qa.where(qa.eq(1), 0)) \
                 .And(qa.where(qa.eq(2), 0)) \
                 .And(qa.where(qa.eq(7), 0)) \
                 .And(qa.where(qa.eq(8), 0)) \
                 .And(qa.where(qa.eq(9), 0)) \
                 .And(qa.where(qa.eq(10), 0))
        return image.updateMask(mask)

    # === 3️⃣ Ảnh mùa mưa ===
    rs_composite = (
        s2.filterDate(startdate_after, enddates)
        .map(maskS2clouds)
        .select(['B2','B3','B4','B5','B6','B7','B8','B11','B12'])
    )
    S2_RS = rs_composite.median().clip(roi)

    # === 4️⃣ Ảnh mùa sau mưa ===
    prs_composite = (
        s2.filterDate(startdate_before, startdate_after)
        .map(maskS2clouds)
        .select(['B2','B3','B4','B5','B6','B7','B8','B11','B12'])
    )
    S2_PRS = prs_composite.median().clip(roi)

    # === 5️⃣ Ảnh mùa khô ===
    ds_composite = (
        s2.filterDate(enddates.advance(-11, 'month'), enddates)
        .map(maskS2clouds)
        .select(['B2','B3','B4','B5','B6','B7','B8','B11','B12'])
    )
    S2_DS = ds_composite.median().clip(roi)

    # === 6️⃣ Sentinel-1 dữ liệu ===
    def get_S1_iqr(start, end):
        s1 = (
            ee.ImageCollection('COPERNICUS/S1_GRD')
            .filterDate(start, end)
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
            .filter(ee.Filter.eq('instrumentMode', 'IW'))
            .filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING'))
            .filterBounds(roi)
        )

        s1_pc = s1.reduce(ee.Reducer.percentile([25, 50, 75]))
        s1_pc = ee.Image(10).pow(s1_pc.divide(10))
        feats = s1_pc.select(['VH_p50','VV_p50']).clip(roi)
        VV_iqr = s1_pc.select('VV_p75').subtract(s1_pc.select('VV_p25')).rename('VV_iqr')
        VH_iqr = s1_pc.select('VH_p75').subtract(s1_pc.select('VH_p25')).rename('VH_iqr')
        return feats.addBands(VV_iqr).addBands(VH_iqr)

    S1_RS = get_S1_iqr(startdate_after, enddates)
    S1_PRS = get_S1_iqr(startdate_before, startdate_after)
    S1_DS = get_S1_iqr(enddates.advance(-11, 'month'), enddates)

    # === 7️⃣ DEM và độ dốc ===
    SRTM = ee.Image("USGS/SRTMGL1_003")
    elevation = SRTM.clip(roi)
    slope = ee.Terrain.slope(SRTM).clip(roi)

    # === 8️⃣ Kết hợp toàn bộ biến đầu vào ===
    input_features = (
        S2_RS
        .addBands(S2_PRS)
        .addBands(S2_DS)
        .addBands(S1_RS)
        .addBands(S1_PRS)
        .addBands(S1_DS)
        .addBands(elevation)
        .addBands(slope)
        .clip(roi)
    )

    # === 9️⃣ Raster huấn luyện (giả sử đã có esri_lulc10) ===
    def remapper(image):
        return image.remap([1,2,4,5,7,8,9,10,11], [1,2,3,4,5,6,7,8,9])

    training_rasterized = esri_lulc10.map(remapper).mosaic().clip(roi)
    input_features = input_features.addBands(training_rasterized.toInt().rename('class'))

    # === 🔟 Lấy mẫu dữ liệu huấn luyện ===
    training_dataset = input_features.stratifiedSample(
        numPoints=10000,
        classBand='class',
        region=roi,
        scale=30
    )

    training_dataset = training_dataset.randomColumn('random', 50)
    split = 0.7
    Sample_training = training_dataset.filter(ee.Filter.lt('random', split))

    bands = ['B2', 'B3','B4','B8','B11','B12','VV_iqr','VH_iqr','elevation','slope']

    # === 11️⃣ Huấn luyện mô hình CART (hoặc RF) ===
    classifier = ee.Classifier.smileCart().train(
        features=Sample_training,
        classProperty='class',
        inputProperties=bands
    )

    # === 12️⃣ Phân loại ===
    classified = input_features.select(bands).classify(classifier).clip(roi)
    mode_classified = classified.focal_mode(1)

    return mode_classified

def magnitude(image):
    return image.pow(2).reduce('sum').sqrt().rename('class')

def landuser_layers():
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    enddate_now = request.args.get('end')

    # --- Xác định ROI ---
    try:
        if not district:
            shapefile_path = f"public/commune/hcxa2025_{province}.shp"
            import os
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

    # --- Chuyển ngày sang ee.Date ---
    enddate_now_ee = ee.Date(enddate_now)
    enddate_prev_ee = enddate_now_ee.advance(-1, 'month')

    # --- Phân loại đất đai hai thời điểm ---
    Classified_before = classify_landuser(roi, enddate_prev_ee)
    Classified_now = classify_landuser(roi, enddate_now_ee)

    # --- Tính sự khác biệt ---
    difference = magnitude(Classified_now.subtract(Classified_before)).toInt()
    landuser_same = difference.eq(0)
    landuser_diff = Classified_now.updateMask(landuser_same.Not()).rename('class')

    esri_lulc10 = ee.ImageCollection('projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m')
    def remapper(image):
        return image.remap([1,2,4,5,7,8,9,10,11], [1,2,3,4,5,6,7,8,9])

    training_rasterized = esri_lulc10.map(remapper).mosaic().clip(roi)

    same_class_mask = landuser_diff.eq(training_rasterized)

    landuser_same_class = landuser_diff.updateMask(same_class_mask).rename('class')


    # --- Định nghĩa các lớp riêng lẻ ---
    remap_lists = {
        'Mặt nước':      ([1,2,3,4,5,6,7,8,9], [1,0,0,0,0,0,0,0,0]),
        'Rừng, cây lâu năm':      ([1,2,3,4,5,6,7,8,9], [0,1,0,0,0,0,0,0,0]),
        'Đồng cỏ, cây bụi':      ([1,2,3,4,5,6,7,8,9], [0,0,1,0,0,0,0,0,0]),
        'Đất nông nghiệp':      ([1,2,3,4,5,6,7,8,9], [0,0,0,1,0,0,0,0,0]),
        'Núi đá, đất trống':      ([1,2,3,4,5,6,7,8,9], [0,0,0,0,0,1,0,0,0]),
        'Đất ở, đất đô thị': ([1,2,3,4,5,6,7,8,9], [0,0,0,0,1,0,0,0,0]),
    }

    # --- Palette màu tương ứng ---
    palettes = {
        'Mặt nước': ["#064696"],
        'Rừng, cây lâu năm': ["#35B814"],
        'Đồng cỏ, cây bụi': ["#77146F"],
        'Đất nông nghiệp': ["#FCC80E"],
        'Núi đá, đất trống': ["#141414"],
        'Đất ở, đất đô thị': ["#F8062F"]
    }

    # --- Lưu tile URL cho tất cả lớp ---
    tiles = {}
    pixel_area = ee.Image.pixelArea().divide(10000)

    for name, (from_vals, to_vals) in remap_lists.items():
        layer = landuser_same_class.remap(from_vals, to_vals).updateMask(
            landuser_same_class.remap(from_vals, to_vals).eq(1)
        ).rename('class')

        vis_params = {'palette': palettes[name], 'min': 1, 'max': 1}
        map_dict = layer.getMapId(vis_params)
        if 'tile_fetcher' in map_dict:
            tile_url = map_dict['tile_fetcher'].url_format
        elif 'mapid' in map_dict and 'token' in map_dict:
            tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
        else:
            tile_url = None

        area = layer.multiply(pixel_area).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=10,
            maxPixels=9e13,
            tileScale=4
        ).get('class')
        area_ha = area.getInfo() if area else 0

        # --- per-commune breakdown ---
        area_ha_by_commune = None
        try:
            shapefile_path = f"public/commune/hcxa2025_{province}.shp"
            import os
            if os.path.exists(shapefile_path):
                gdf2 = gpd.read_file(shapefile_path)
                if 'tenxa' in gdf2.columns:
                    if district and str(district).strip():
                        gdf2['tenxa_norm'] = gdf2['tenxa'].astype(str).str.lower().str.strip()
                        if isinstance(district, str) and ',' in district:
                            parts = [d.strip().lower() for d in district.split(',') if d.strip()]
                        elif isinstance(district, (list, tuple)):
                            parts = [str(d).strip().lower() for d in district if str(d).strip()]
                        else:
                            parts = [str(district).strip().lower()]
                        gdf2 = gdf2[gdf2['tenxa_norm'].isin(parts)]

                    if not gdf2.empty:
                        commune_gdf = gdf2.loc[gdf2.geometry.notna()].copy()
                        commune_gdf['tenxa_norm'] = commune_gdf['tenxa'].astype(str).str.lower().str.strip()
                        commune_gdf = commune_gdf.dissolve(by='tenxa_norm', as_index=False, aggfunc={'tenxa': 'first'})

                        commune_features = []
                        for _, row in commune_gdf.iterrows():
                            if row.geometry is None or row.geometry.is_empty:
                                continue
                            commune_features.append(
                                ee.Feature(ee.Geometry(row.geometry.__geo_interface__), {'tenxa': row['tenxa']})
                            )

                        if commune_features:
                            commune_fc = ee.FeatureCollection(commune_features)
                            commune_area_fc = layer.multiply(pixel_area).reduceRegions(
                                collection=commune_fc,
                                reducer=ee.Reducer.sum(),
                                scale=10
                            )
                            commune_area_info = commune_area_fc.getInfo()
                            area_ha_by_commune = []
                            for feature in commune_area_info.get('features', []):
                                props = feature.get('properties', {})
                                area_ha_commune = props.get('sum') or 0
                                area_ha_by_commune.append({'tenxa': props.get('tenxa'), 'area_ha': round(area_ha_commune, 4)})
                            area_ha_by_commune.sort(key=lambda item: item['area_ha'], reverse=True)
        except Exception:
            area_ha_by_commune = None

        tiles[name] = {
            'tile_url': tile_url,
            'area_ha': area_ha,
            'palette': palettes[name],
            'area_ha_by_commune': area_ha_by_commune
        }

    return jsonify(tiles)
