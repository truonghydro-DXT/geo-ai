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

# end = '2025-02-20'
# province = 'tinhGiaLai'
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


def get_commune_roi(province, district):
    import os
    shapefile_path = f"public/commune/hcxa2025_{province}.shp"
    if not os.path.exists(shapefile_path):
        raise ValueError(f"Shapefile not found: {shapefile_path}")

    gdf = gpd.read_file(shapefile_path)
    gdf['tenxa_norm'] = gdf['tenxa'].astype(str).str.lower().str.strip()

    # support CSV
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


def rain_temp_drought(regions, start_time, end_time):
    """
    regions: ee.Geometry / ee.Feature / ee.FeatureCollection
    start_time, end_time: 'YYYY-MM-dd' (string) hoặc ee.Date
    Trả về: (pcp_ratio, temp_ratio)
    """
    lable_pcp = "total_precipitation_mm"
    lable_temp = "temperature_C"

    # --- Datasets ---
    ERA5_daily = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
    ERA5_monthly = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR")

    # --- Converters ---
    def mtomm(img):
        return img.select("total_precipitation_sum").multiply(1000).rename(lable_pcp).copyProperties(img, ['system:time_start','system:time_end'])
    def ktoc(img):
        return img.select("temperature_2m").subtract(273.15).rename(lable_temp).copyProperties(img, ['system:time_start','system:time_end'])

    ERA5_precip = ERA5_daily.map(mtomm)
    ERA5_temp_monthly = ERA5_monthly.map(ktoc)

    # --- Reduce helper ---
    def reduce_mean(image, label):
        return image.select(label).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=regions,
            scale=1000,
            bestEffort=True,
            maxPixels=1e13
        )

    # --- Chuẩn hóa thời gian ---
    start_date = ee.Date(start_time)
    end_date = ee.Date(end_time)
    year_now = ee.Number(end_date.get('year')).int()

    start_month = ee.Number(start_date.get('month'))
    end_month = ee.Number(end_date.get('month'))

    list_dayofmonth = ee.List([31,28,31,30,31,30,31,31,30,31,30,31])

    # --- Xử lý qua năm ---
    def fix_date(y, sm, em):
        """
        Tạo khoảng thời gian (s, e) đúng khi sm > em (qua năm).
        """
        y = ee.Number(y)
        s = ee.Date.fromYMD(y, sm, 1)
        e = ee.Algorithms.If(
            sm.gt(em),  # nếu tháng đầu > tháng cuối => sang năm sau
            ee.Date.fromYMD(y.add(1), em, ee.Number(list_dayofmonth.get(em.subtract(1)))),
            ee.Date.fromYMD(y, em, ee.Number(list_dayofmonth.get(em.subtract(1))))
        )
        return ee.List([s, e])

    # --- Lượng mưa hiện tại ---
    pcp_map = ERA5_precip.filterDate(start_date, end_date).select(lable_pcp).sum().clip(regions)
    pcp_now_dict = reduce_mean(pcp_map, lable_pcp)
    pcp_now_mean = ee.Number(ee.Dictionary(pcp_now_dict).get(lable_pcp))

    # --- Tính trung bình nhiều năm ---
    years = ee.List.sequence(2000, year_now)

    def per_year_sum(y):
        y = ee.Number(y).int()
        dates = fix_date(y, start_month, end_month)
        s = ee.Date(dates.get(0))
        e = ee.Date(dates.get(1))
        img = ERA5_precip.filterDate(s, e).select(lable_pcp).sum().clip(regions)
        return img.set('year', y)

    hist_col = ee.ImageCollection(years.map(per_year_sum))
    hist_mean_img = hist_col.mean().clip(regions)
    pcp_hist_dict = reduce_mean(hist_mean_img, lable_pcp)
    pcp_hist_mean = ee.Number(ee.Dictionary(pcp_hist_dict).get(lable_pcp))

    pcp_ratio = ee.Algorithms.If(
        pcp_hist_mean.gt(0),
        pcp_now_mean.divide(pcp_hist_mean).multiply(100),
        ee.Number(0)
    )
    pcp_ratio = ee.Number(pcp_ratio)

    # --- Nhiệt độ ---
    temp_map = ERA5_temp_monthly.filterDate(start_date, end_date).select(lable_temp).mean().clip(regions)
    temp_cur_dict = reduce_mean(temp_map, lable_temp)
    temp_cur_mean = ee.Number(ee.Dictionary(temp_cur_dict).get(lable_temp))

    def temp_per_year(y):
        y = ee.Number(y).int()
        dates = fix_date(y, start_month, end_month)
        s = ee.Date(dates.get(0))
        e = ee.Date(dates.get(1))
        return ERA5_temp_monthly.filterDate(s, e).select(lable_temp).mean().clip(regions)

    temp_hist_col = ee.ImageCollection(years.map(temp_per_year))
    temps_map = temp_hist_col.mean().clip(regions)
    temps_map_dict = reduce_mean(temps_map, lable_temp)
    temp_hist_mean = ee.Number(ee.Dictionary(temps_map_dict).get(lable_temp))

    temp_ratio = ee.Algorithms.If(
        temp_hist_mean.gt(0),
        temp_cur_mean.divide(temp_hist_mean).subtract(1),
        ee.Number(0)
    )
    temp_ratio = ee.Number(temp_ratio)

    return pcp_ratio, temp_ratio


def drought_area():
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    try:
        if not district:
            shapefile_path = f"public/commune/hcxa2025_{province}.shp"
            import os
            if not os.path.exists(shapefile_path):
                return jsonify({'error': f'Shapefile not found: {shapefile_path}'}), 404
            gdf = gpd.read_file(shapefile_path)
            union_geom = gdf.unary_union
            region = ee.Geometry(union_geom.__geo_interface__)
        else:
            region = get_commune_roi(province, district)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': 'Lỗi khi xây dựng vùng quan tâm: ' + str(e)}), 500

    # --- 2️⃣ Mask vùng cây trồng ---
    ESA_WorldCover = ee.ImageCollection("ESA/WorldCover/v200") \
    .first() \
    .select('Map')

    # Cắt vùng nghiên cứu
    ESA_LC_2022 = ESA_WorldCover.clip(region)

    # Tạo mask vùng cây trồng: class 20, 30, 40
    area_crop_mask = ESA_LC_2022.updateMask(
        ESA_LC_2022.eq(20)
        .Or(ESA_LC_2022.eq(30))
        .Or(ESA_LC_2022.eq(40))
    )

    # --- 3️⃣ Thời gian ---
    endDate = ee.Date(end)
    startDate = endDate.advance(-3, 'month')

    # --- 4️⃣ Kiểm tra điều kiện khí tượng ---
    pcp_ratio, temp_ratio = rain_temp_drought(
        region, startDate.format("YYYY-MM-dd"), endDate.format("YYYY-MM-dd")
    )

    pcp_value = pcp_ratio.getInfo()
    temp_value = temp_ratio.getInfo()
    # print(pcp_value, temp_value)

    # --- 5️⃣ Điều kiện hạn ---
    if temp_value > 0.01 and pcp_value < 80:
        active = 1

        dataset = (
            ee.ImageCollection('LANDSAT/LC08/C02/T1_TOA')
            .filterDate('2014-01-01', endDate)
            .filter(ee.Filter.lt('CLOUD_COVER', 60))
            .filterBounds(region)
        )

        # Ảnh trung bình dài hạn & hiện tại
        image_timeseries = dataset.mosaic().clip(region).reproject(crs='EPSG:3857', scale=30)
        image_current = dataset.filter(ee.Filter.date(startDate, endDate)).mosaic().clip(region).reproject(crs='EPSG:3857', scale=30)

        # --- NDVI ---
        NDVI_timeseries = image_timeseries.normalizedDifference(['B5', 'B4']).rename('NDVI')

        NDVI_min = NDVI_timeseries.reduceRegion(
            reducer=ee.Reducer.min(),
            scale=30,
            crs='EPSG:3857',
            geometry=region,
            bestEffort=True,
            tileScale=16
        )

        NDVI_max = NDVI_timeseries.reduceRegion(
            reducer=ee.Reducer.max(),
            scale=30,
            crs='EPSG:3857',
            geometry=region,
            bestEffort=True,
            tileScale=16
        )

        NDVI_current = image_current.normalizedDifference(['B5', 'B4']).rename('NDVI')

        # --- 6️⃣ Tính chỉ số VCI ---
        NDVI_min = NDVI_timeseries.reduceRegion(
            reducer=ee.Reducer.min(),
            scale=30,
            crs='EPSG:3857',
            geometry=region,
            bestEffort=True,
            tileScale=16
        )
        NDVI_max = NDVI_timeseries.reduceRegion(
            reducer=ee.Reducer.max(),
            scale=30,
            crs='EPSG:3857',
            geometry=region,
            bestEffort=True,
            tileScale=16
        )

        # --- 6️⃣ Tính chỉ số VCI ---
        VCI_image = NDVI_current.updateMask(area_crop_mask).expression(
            '(Ia - Imin) / (Imax - Imin)',
            {
                'Ia': NDVI_current.updateMask(area_crop_mask),
                'Imin': ee.Image.constant(ee.Number(NDVI_min.get('NDVI'))),
                'Imax': ee.Image.constant(ee.Number(NDVI_max.get('NDVI')))
            }
        ).rename('VCI')

        VCI_image = VCI_image.focal_median(100, 'circle', 'meters')

        drought_class = VCI_image.expression(
            "(vci <= 0.1) ? 1 : "
            "(vci <= 0.3) ? 2 : "
            "(vci <= 0.5) ? 3 : "
            "(vci <= 0.7) ? 4 : 5",
            {'vci': VCI_image}
        ).rename('drought_class')

    
        # create both masked and unmasked display images so we can fallback if mask removes all pixels
        drought_class_display_unmasked = drought_class.updateMask(drought_class.neq(5))
        drought_class_display_masked = drought_class_display_unmasked.updateMask(area_crop_mask)


        class_values = {
            'Nguy cơ rất cao': 1,
            'Nguy cơ cao': 2,
            'Nguy cơ trung bình': 3,
            'Nguy cơ thấp': 4
        }

        palettes = {
            'Nguy cơ rất cao': ["#FF00F2"],
            'Nguy cơ cao': ["#FC0F0F"],
            'Nguy cơ trung bình': ["#F77621"],
            'Nguy cơ thấp': ["#CAC840"]
        }
        scale = 30
        tiles = {}
        pixel_area = ee.Image.pixelArea().divide(10000)

        # Load commune geometries once for all classes
        
        commune_fc = None
        commune_names = []
        try:
            shapefile_path = f"public/commune/hcxa2025_{province}.shp"
            import os
            if os.path.exists(shapefile_path):
                gdf_commune = gpd.read_file(shapefile_path)
                if "tenxa" in gdf_commune.columns:
                    commune_gdf = gdf_commune.loc[gdf_commune.geometry.notna()].copy()
                    commune_gdf['tenxa_norm'] = commune_gdf['tenxa'].astype(str).str.lower().str.strip()
                    if district and str(district).strip():
                        if isinstance(district, str) and ',' in district:
                            parts = [d.strip().lower() for d in district.split(',') if d.strip()]
                        elif isinstance(district, (list, tuple)):
                            parts = [str(d).strip().lower() for d in district if str(d).strip()]
                        else:
                            parts = [str(district).strip().lower()]
                        commune_gdf = commune_gdf[commune_gdf['tenxa_norm'].isin(parts)]

                    commune_gdf = commune_gdf.dissolve(by='tenxa_norm', as_index=False, aggfunc={'tenxa': 'first'})
                    commune_features = []
                    for _, row in commune_gdf.iterrows():
                        if row.geometry is None or row.geometry.is_empty:
                            continue
                        commune_names.append(row['tenxa'])
                        commune_features.append(
                            ee.Feature(
                                ee.Geometry(row.geometry.__geo_interface__),
                                {'tenxa': row['tenxa']}
                            )
                        )
                    if commune_features:
                        commune_fc = ee.FeatureCollection(commune_features)
        except Exception as ex:
            print('Error preparing commune geometries:', ex)

        for name, class_value in class_values.items():
            layer = drought_class_display_masked.eq(class_value).selfMask().rename('class')
            class_area_image = layer.multiply(pixel_area).rename('class')

            vis_params = {'palette': palettes[name], 'min': 1, 'max': 1}
            map_dict = layer.getMapId(vis_params)
            if 'tile_fetcher' in map_dict:
                tile_url = map_dict['tile_fetcher'].url_format
            elif 'mapid' in map_dict and 'token' in map_dict:
                tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
            else:
                tile_url = None

            area = class_area_image.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=region,
                scale=scale,
                maxPixels=9e13,
                tileScale=4
            ).get('class')
            area_ha = area.getInfo() if area is not None else 0

            # commune breakdown for this class
            class_area_by_commune = []
            if commune_fc is not None:
                commune_area_fc = class_area_image.reduceRegions(
                    collection=commune_fc,
                    reducer=ee.Reducer.sum(),
                    scale=scale,
                    tileScale=4
                )
                commune_area_info = commune_area_fc.getInfo()
                for feature in commune_area_info.get('features', []):
                    props = feature.get('properties', {})
                    class_area_by_commune.append({
                        'tenxa': props.get('tenxa'),
                        'area_ha': round(float(props.get('sum') or 0), 4)
                    })
                class_area_by_commune.sort(key=lambda item: item['area_ha'], reverse=True)

            tiles[name] = {
                'tile_url': tile_url,
                'area_ha': area_ha,
                'palette': palettes[name],
                'area_ha_by_commune': class_area_by_commune
            }

        return jsonify(tiles)

    # Không đủ điều kiện khí tượng để cảnh báo hạn
    return jsonify({'active': 0})

# drought_area()