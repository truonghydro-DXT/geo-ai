import ee, json
import geopandas as gpd
from flask import request, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta 
import numpy as np

def model_image(region, year_nows, month_nows, day_nows):
    global image_S12
    endDates = ee.Date.fromYMD(year_nows, month_nows, day_nows).format('YYYY-MM-dd')
    startDates = ee.Date(endDates).advance(-45, 'day').format('YYYY-MM-dd')
    bandS2 = ['B2','B3','B4','B5','B8', 'B8A', 'B9', 'B11','B12']
    # Mask cloud
    def maskClouds(img):
        MAX_CLOUD_PROBABILITY = 75
        clouds = ee.Image(img.get('cloud_mask')).select('probability')
        isNotCloud = clouds.lt(MAX_CLOUD_PROBABILITY)
        return img.updateMask(isNotCloud)

    def maskEdges(s2_img):
        return s2_img.updateMask(
            s2_img.select('B8A').mask().updateMask(s2_img.select('B9').mask()))

    s2Sr = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').select(bandS2)
    s2Clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
    criteria = ee.Filter.And(
        ee.Filter.bounds(region),
        ee.Filter.date(startDates, endDates)
    )
    s2Sr = s2Sr.filter(criteria).map(maskEdges)
    s2Clouds = s2Clouds.filter(criteria)
    condition = ee.Filter.equals(leftField='system:index', rightField='system:index')
    s2SrWithCloudMask = ee.Join.saveFirst('cloud_mask').apply(
        primary=s2Sr,
        secondary=s2Clouds,
        condition=condition
    )

    S2_SR = ee.ImageCollection(s2SrWithCloudMask).map(maskClouds).mosaic().clip(region)

    red = S2_SR.select('B4').multiply(0.0001)
    nir = S2_SR.select('B8').multiply(0.0001)
    swir = S2_SR.select('B12').multiply(0.0001)

    alpha = ee.Image(0.51)
    ndpi = (nir.subtract(alpha.multiply(red).add((ee.Image(1).subtract(alpha)).multiply(swir)))).divide(nir.add(alpha.multiply(red).add((ee.Image(1).subtract(alpha)).multiply(swir)))).rename('NDPI')

    ndvi = S2_SR.expression('(nir - red) / (red + nir)', {
               'nir': S2_SR.select('B8').multiply(0.0001),
               'red': S2_SR.select('B4').multiply(0.0001)
           }).select([0], ['NDVI'])

    ndvi_index = S2_SR.expression ('float ((((NIR - RED) / (NIR + RED)) + 1) * 128)',{
              'NIR': S2_SR.select('B8'),
              'RED': S2_SR.select('B4')}).rename('NDVI_index')

    savi = S2_SR.expression('((NIR - Red) / (NIR + Red + 0.5)) * (1.0 + 0.5)',{
          'NIR':S2_SR.select('B8'),
          'Red':S2_SR.select('B4')
          }).rename('SAVI')

    gndvi = S2_SR.expression ('float ((NIR - GREEN) / (NIR + GREEN))', {
                'GREEN':S2_SR.select ('B3'),
                'NIR':S2_SR.select ('B8')
            }).rename('GNDVI')

    evi = S2_SR.expression ('float (2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)))', {
                  'NIR':S2_SR.select ('B8'),
                  'RED':S2_SR.select ('B4'),
                  'BLUE':S2_SR.select ('B2')
                }).rename('EVI')

    evi2 =  S2_SR.expression ('float (2.5 * (NIR - RED) / (NIR + 2.4*RED + 1.0))', {
              'NIR':S2_SR.select ('B8'),
              'RED':S2_SR.select ('B4')
              }).rename('EVI2')

    ndre = S2_SR.expression ('float ((NIR - Rededge)/( NIR + Rededge))', {
              'Rededge':S2_SR.select ('B5'),
              'NIR':S2_SR.select ('B8')
              }).rename('NDRE')

     #Load SRTM
    SRTM = ee.Image("USGS/SRTMGL1_003")

    #Derive slope from the SRTM
    slope = ee.Terrain.slope(SRTM)

    S2_collection = S2_SR.addBands(ndvi.addBands(ndvi_index.addBands(savi.addBands(gndvi.addBands(evi.addBands(evi2.addBands(ndre.addBands(slope.addBands(ndpi)))))))))

    # Load Sentinel-1
    sentinel1 = ee.ImageCollection('COPERNICUS/S1_GRD') \
            .filterBounds(region)\
            .filterDate(startDates, endDates)\

    # Filter by metadata properties.
    vh = sentinel1 \
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
      .filter(ee.Filter.eq('instrumentMode', 'IW'))

    # Filter to get images from different look angles.
    vhAscending = vh.filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING'))
    vhDescending = vh.filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))

    # Create a composite from means at different polarizations and look angles.
    S1_collection = ee.Image.cat([
      vhAscending.select('VH').mean(),
      ee.ImageCollection(vhAscending.select('VV').merge(vhDescending.select('VV'))).mean(),
      vhDescending.select('VH').mean()
    ]).focal_median()

    image_S12 = ee.Image.cat([S1_collection,S2_collection]).clip(region)
    return image_S12

def model_training(region, provid, year_nows, month_nows, day_nows, crop_mask, rice_mask, band_train,crop_mask_NoRice):
    global training, slope_mask
    
    image = model_image(region, year_nows, month_nows, day_nows)
    texture = image.select('VV').toInt32().glcmTexture(**{'size': 4})
    entropy = texture.select('VV_ent').updateMask(crop_mask)

    # Creat point for Rice
    ckeck_prov1 = ['tinhCaoBang', 'tinhTuyenQuang', 'tinhLaoCai', 'tinhDienBien', 'tinhLaiChau', 'tinhSonLa', 'tinhThaiNguyen', 'tinhLangSon', 'tinhQuangNinh', 'tinhBacNinh', 'tinhPhuTho']
    ckeck_prov2 = ['tinhThanhHoa', 'tinhNgheAn', 'tinhHaTinh', 'tinhQuangTri', 'tpHue']
    ckeck_prov3 = ['tpDaNang', 'tinhQuangNgai', 'tinhKhanhHoa', 'tinhGiaLai', 'tinhDakLak', 'tinhLamDong']


    if provid in ckeck_prov1:
        #band_train = ['VV', 'VH']
        slope_mask = image.select('slope').lt(30).updateMask(crop_mask)
        rice_region = ee.Image(1) \
                    .where (image.select('NDVI_index').lt(170).reduce('sum').toInt().And(image.select('NDVI_index').gt(190).reduce('sum').toInt()), 1) \
                    .where (image.select('NDVI_index').gte(170).reduce('sum').toInt().And(image.select('NDVI_index').lte(190).reduce('sum').toInt()), 2)
    if provid in ckeck_prov3:
       #band_train = ['VV', 'VH']
        slope_mask = image.select('slope').lt(20).updateMask(crop_mask)
        rice_region = ee.Image(1) \
                    .where (image.select('NDVI_index').lt(165).reduce('sum').toInt().And(image.select('NDVI_index').gt(190).reduce('sum').toInt()), 1) \
                    .where (image.select('NDVI_index').gte(165).reduce('sum').toInt().And(image.select('NDVI_index').lte(190).reduce('sum').toInt()), 2)
    else:
        slope_mask = image.select('slope').lt(10).updateMask(crop_mask)
        rice_region = ee.Image(1) \
                    .where (image.select('NDVI_index').lt(160).reduce('sum').toInt().And(image.select('NDVI_index').gt(190).reduce('sum').toInt()), 1) \
                    .where (image.select('NDVI_index').gte(160).reduce('sum').toInt().And(image.select('NDVI_index').lte(190).reduce('sum').toInt()), 2)

    rice_region = rice_region.updateMask(rice_mask).clip(region)
    rice_region = rice_region.updateMask(rice_region.eq(2))
    image_train = image.select(band_train)

    image_train_rice = image_train.updateMask(rice_region)
    # Make the training dataset.
    training_rice = image_train_rice.sample(
        **{
            'region': region,
            'scale': 30,
            'numPixels': 1000,
            'tileScale':16,
            'geometries': True,  # Set this to False to ignore geometries
            #'seed': 20,
        }
    )

    # Creat point for Cassava
    cassava_region = ee.Image(1) \
                .where (image.select('GNDVI').lt(0.25).reduce('sum').toInt().And(image.select('GNDVI').gt(0.31).reduce('sum').toInt()), 1) \
                .where (image.select('GNDVI').gte(0.25).reduce('sum').toInt().And(image.select('GNDVI').lte(0.31).reduce('sum').toInt()), 2)

    cassava_region = cassava_region.updateMask(crop_mask_NoRice).updateMask(entropy.lt(2.3)).clip(region)
    cassava_region = cassava_region.updateMask(crop_mask_NoRice).eq(2)

    image_train_cassava = image_train.updateMask(cassava_region)
    # Make the training dataset.
    training_cassava = image_train_cassava.sample(
        **{
            'region': region,
            'scale': 30,
            'numPixels': 1000,
            'tileScale':16,
            'geometries': True,  # Set this to False to ignore geometries
            #'seed': 20,
        }
    )

    # Creat point for Legume
    legume_region = ee.Image(1) \
                .where(image.select('EVI2').lt(0.8).reduce('sum').toInt().And(image.select('EVI2').gt(1.46).reduce('sum').toInt()), 1) \
                .where(image.select('EVI2').gte(0.8).reduce('sum').toInt().And(image.select('EVI2').lte(1.46).reduce('sum').toInt()), 2)

    legume_region = legume_region.updateMask(crop_mask_NoRice).updateMask(entropy.lt(2.5)).clip(region)
    legume_region = legume_region.updateMask(crop_mask_NoRice).eq(2)

    image_train_legume = image_train.updateMask(legume_region)
    # Make the training dataset.
    training_legume = image_train_legume.sample(
        **{
            'region': region,
            'scale': 30,
            'numPixels': 1000,
            'tileScale':16,
            'geometries': True,  # Set this to False to ignore geometries
            #'seed': 20,
        }
    )

    # Creat point for Maize
    Kc = ee.Image(-0.11).add(ee.Image(0.94).multiply(image.select('SAVI'))).rename('kc')
    maize_region = ee.Image(1) \
                 .where(Kc.select('kc').lt(0.27).reduce('sum').toInt().And(Kc.select('kc').gt(0.51).reduce('sum').toInt()), 1) \
                 .where(Kc.select('kc').gte(0.27).reduce('sum').toInt().And(Kc.select('kc').lte(0.51).reduce('sum').toInt()), 2)

    maize_region = maize_region.updateMask(crop_mask_NoRice).updateMask(entropy.lt(2.7)).clip(region)
    maize_region = maize_region.updateMask(crop_mask_NoRice).eq(2)

    image_train_maize = image_train.updateMask(maize_region)
    # Make the training dataset.
    training_maize = image_train_maize.sample(
        **{
            'region': region,
            'scale': 30,
            'numPixels': 1000,
            'tileScale':16,
            'geometries': True,  # Set this to False to ignore geometries
            #'seed': 20,
        }
    )

    # Creat point for Potato
    potato_region = ee.Image(1) \
                .where(image.select('EVI').lt(0.21).reduce('sum').toInt().And(image.select('EVI').gt(0.51).reduce('sum').toInt()), 1) \
                .where(image.select('EVI').gte(0.21).reduce('sum').toInt().And(image.select('EVI').lte(0.51).reduce('sum').toInt()), 2)

    potato_region = potato_region.updateMask(crop_mask_NoRice).updateMask(entropy.lt(1.7)).clip(region)
    potato_region = potato_region.updateMask(crop_mask_NoRice).eq(2)

    image_train_potato = image_train.updateMask(potato_region)
    # Make the training dataset.
    training_potato = image_train_potato.sample(
        **{
            'region': region,
            'scale': 30,
            'numPixels': 1000,
            'tileScale':16,
            'geometries': True,  # Set this to False to ignore geometries
            #'seed': 20,
        }
    )

    # Creat point for Sugar
    sugar_region = ee.Image(1) \
                .where (image.select('GNDVI').lt(0.11).reduce('sum').toInt().And(image.select('GNDVI').gt(0.35).reduce('sum').toInt()), 1) \
                .where (image.select('GNDVI').gte(0.11).reduce('sum').toInt().And(image.select('GNDVI').lte(0.35).reduce('sum').toInt()), 2)

    sugar_region = sugar_region.updateMask(crop_mask_NoRice).updateMask(entropy.lt(1.9)).clip(region)
    sugar_region = sugar_region.updateMask(crop_mask_NoRice).eq(2)

    image_train_sugar = image_train.updateMask(sugar_region)
    # Make the training dataset.
    training_sugar = image_train_sugar.sample(
        **{
            'region': region,
            'scale': 30,
            'numPixels': 1000,
            'tileScale':16,
            'geometries': True,  # Set this to False to ignore geometries
            #'seed': 20,
        }
    )

    training_rice = training_rice.map(lambda feature: feature.set('class', 1))
    training_cassava = training_cassava.map(lambda feature: feature.set('class', 2))
    training_maize = training_maize.map(lambda feature: feature.set('class', 4))
    #training_potato = training_potato.map(lambda feature: feature.set('class', 5))
    if provid in ckeck_prov1:
        training_legume = training_legume.map(lambda feature: feature.set('class', 6))
        training_sugar = training_sugar.map(lambda feature: feature.set('class', 3))
        training_potato = training_potato.map(lambda feature: feature.set('class', 5))
    elif provid in ckeck_prov2:
        training_legume = training_legume.map(lambda feature: feature.set('class', 5))
        training_sugar = training_sugar.map(lambda feature: feature.set('class', 6))
        training_potato = training_potato.map(lambda feature: feature.set('class', 3))
    else:
        training_legume = training_legume.map(lambda feature: feature.set('class', 3))
        training_sugar = training_sugar.map(lambda feature: feature.set('class', 6))
        training_potato = training_potato.map(lambda feature: feature.set('class', 5))

    training = training_rice.merge(training_cassava).merge(training_legume).merge(training_maize).merge(training_potato).merge(training_sugar)
    return training

def agri_layer():
    end = request.args.get('end')
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    year = end_dt.year
    month = end_dt.month
    day = end_dt.day
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')

    def get_commune_region(province, district):
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

    # --- 1️⃣ Xác định vùng phân tích ---
    try:
        if not district:
            shapefile_path = f"public/commune/hcxa2025_{province}.shp"
            if not os.path.exists(shapefile_path):
                return jsonify({'error': f'Shapefile not found: {shapefile_path}'}), 404
            gdf = gpd.read_file(shapefile_path)
            union_geom = gdf.unary_union
            region = ee.Geometry(union_geom.__geo_interface__)
        else:
            region = get_commune_region(province, district)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': 'Lỗi khi xây dựng vùng quan tâm: ' + str(e)}), 500
    
    cropland_rice = ee.FeatureCollection('projects/gee-truonghydro/assets/RiceLand_03112023')
    ricedAreaImg = cropland_rice \
    .filter(ee.Filter.notNull(['class'])) \
    .reduceToImage(**{
        'properties': ['class'],
        'reducer': ee.Reducer.first()
    })
    rice_mask = ricedAreaImg.clip(region)

    cropland = ee.FeatureCollection('projects/gee-truonghydro/assets/Cropland_VN_Final')
    landAreaImg = cropland \
    .filter(ee.Filter.notNull(['class'])) \
    .reduceToImage(**{
        'properties': ['class'],
        'reducer': ee.Reducer.first()
    })
    crop_mask = landAreaImg.clip(region)
    cropland = crop_mask.updateMask(rice_mask).unmask().clip(region)
    cropland = crop_mask.updateMask(cropland.eq(0))
    crop_mask_NoRice = crop_mask.updateMask(cropland.eq(1)).clip(region)

    band_train = ['B11','B12','VV', 'VH']

    training = model_training(region, province, year, month, day, crop_mask, rice_mask, band_train,crop_mask_NoRice)
    image = model_image(region, year, month, day)
    classifier = ee.Classifier.smileCart().train(training, 'class', band_train)
    image_class = image.select(band_train).updateMask(crop_mask)

    # Classify the image.
    classified = image_class.select(band_train).classify(classifier)
    build_mask = image.select('VH').lt(-15).updateMask(crop_mask)
    classified = classified.updateMask(slope_mask).updateMask(build_mask)

    # 🟩 Danh sách lớp & màu
    palettes = {
        'Cây lúa': ['#00AE72'],
        'Cây sắn': ['#AFD788'],
        'Cây họ đậu': ['#FCE0A6'],
        'Cây ngô': ['#F3C246'],
        'Cây khoai': ['#EE7C6B'],
        'Cây mía': ['#DF0029'],
    }

    remap_lists = {
        'Cây lúa': ([1,2,3,4,5,6], [1,0,0,0,0,0]),
        'Cây sắn': ([1,2,3,4,5,6], [0,1,0,0,0,0]),
        'Cây họ đậu': ([1,2,3,4,5,6], [0,0,1,0,0,0]),
        'Cây ngô': ([1,2,3,4,5,6], [0,0,0,1,0,0]),
        'Cây khoai': ([1,2,3,4,5,6], [0,0,0,0,1,0]),
        'Cây mía': ([1,2,3,4,5,6], [0,0,0,0,0,1]),
    }

    # --- Lưu tile URL cho tất cả lớp ---
    tiles = {}
    pixel_area = ee.Image.pixelArea().divide(10000)

    for name, (from_vals, to_vals) in remap_lists.items():
        layer = classified.remap(from_vals, to_vals).updateMask(
            classified.remap(from_vals, to_vals).eq(1)
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
            geometry=region,
            scale=10,
            maxPixels=1e13
        ).get('class')
        area_ha = area.getInfo() if area else 0

        # per-commune breakdown
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
                            commune_features.append(ee.Feature(ee.Geometry(row.geometry.__geo_interface__), {'tenxa': row['tenxa']}))

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
