import ee, os
import geopandas as gpd
from flask import request, jsonify
from product.algorithm.image_satellite import get_sentinel2_image, get_sentinel2_value, get_commune_roi

def ndvi():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    try:
        if not district:
            shapefile_path = f"demo/commune/hcxa2025_{province}.shp"
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
    s2Masked = get_sentinel2_image(start, end, roi)
    # NDVI
    s2_img = s2Masked.expression(
        '(nir - red) / (nir + red)', {
            'nir': s2Masked.select('B8').multiply(1),
            'red': s2Masked.select('B4').multiply(1)
        }).rename('NDVI')

    vis = {
        'min': -1.0,
        'max': 1.0,
        'palette': [
            '8B0016','B2001F','C50023','DF0029','E54646','EE7C6B','F5A89A',
            'F3C246','F9CC76','FCE0A6','FFFBD1','E6F1D8','C8E2B1','AFD788',
            '67BF7F','00AE72','00A06B','008C5E','007F54','006241'
        ]
    }

    map_dict = s2_img.getMapId(vis)

    # Legend labels khớp với palette
    names = [
        '-1.00 - 0.05: Đất ở, đất trống, mặt nước','0.05 - 0.10: Đất ở, đất trống, mặt nước',
        '0.10 - 0.15: Đất ở, đất trống, mặt nước','0.15 - 0.20: Đất ở, đất trống, mặt nước',
        '0.20 - 0.25: Thảm thực vật thưa thớt','0.25 - 0.30: Thảm thực vật thưa thớt',
        '0.30 - 0.35: Thảm thực vật thưa thớt','0.35 - 0.40: Thảm thực vật thưa thớt',
        '0.40 - 0.45: Thảm thực vật vừa phải','0.45 - 0.50: Thảm thực vật vừa phải',
        '0.50 - 0.55: Thảm thực vật vừa phải','0.55 - 0.60: Thảm thực vật vừa phải',
        '0.60 - 0.65: Thảm thực vật dày đặc','0.65 - 0.70: Thảm thực vật dày đặc',
        '0.70 - 0.75: Thảm thực vật dày đặc','0.75 - 0.80: Thảm thực vật dày đặc',
        '0.80 - 0.85: Thảm thực vật dày đặc','0.85 - 0.90: Thảm thực vật dày đặc',
        '0.90 - 0.95: Thảm thực vật dày đặc','0.95 - 1.00: Thảm thực vật dày đặc'
    ]

    legend = [{"color": "#" + c, "label": names[i]} for i, c in enumerate(vis["palette"])]

    # Lấy tile URL hợp lệ
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({
        'tile_url': tile_url,
        'legend': legend
    })

def ndvi_value():
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    start = request.args.get('start')
    end = request.args.get('end')

    point = ee.Geometry.Point([lon, lat])
    s2 = get_sentinel2_value(start, end, point)

    s2_img = s2.mean().normalizedDifference(['B8','B4']).rename('NDVI')

    value = s2_img.sample(point, scale=10).first().get('NDVI').getInfo()

    return jsonify({'lat': lat, 'lon': lon, 'ndvi': value})

def msavi():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    try:
        if not district:
            shapefile_path = f"demo/commune/hcxa2025_{province}.shp"
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
    s2Masked = get_sentinel2_image(start, end, roi)
    # NDVI
    s2_img = s2Masked.expression('(2 * NIR + 1 - sqrt((2 * NIR + 1) * (2 * NIR + 1) - 8 * (NIR - RED))) / 2',
        {
            'NIR': s2Masked.select('B8'), 
            'RED': s2Masked.select('B4')
        }).rename('MSAVI')

    palette = ['8B0016','B2001F','C50023','DF0029','E54646','EE7C6B','F5A89A',
                  'F3C246','F9CC76','FCE0A6','FFFBD1','E6F1D8','C8E2B1','AFD788',
                  '67BF7F','00AE72','00A06B','008C5E','007F54','006241']

    vis = {
        'min': -1.0,
        'max': 1.0,
        'palette': palette
    }

    map_dict = s2_img.getMapId(vis)

    # Legend labels khớp với palette
        
    names = ['-1.00 - 0.00: Đất ở, đất trống, mặt nước', '0.00 - 0.02: Mới nổi', '0.02 - 0.04: Đâm chồi','0.04 - 0.06: Đâm chồi',
            '0.06 - 0.08: Thảm thực vật thưa thớt', '0.08 - 0.10: Thảm thực vật thưa thớt','0.10 - 0.12: Thảm thực vật thưa thớt', '0.12 - 0.15: Thảm thực vật thấp',
            '0.15 - 0.17: Thảm thực vật thấp','0.17 - 0.20: Thảm thực vật thấp','0.20 - 0.22: Thảm thực vật vừa phải','0.22 - 0.25: Thảm thực vật vừa phải',
            '0.25 - 0.27: Thảm thực vật vừa phải','0.27 - 0.30: Thảm thực vật vừa phải','0.30 - 0.35: Thảm thực vật vừa phải','0.35 - 0.40: Thảm thực vật dày đặc',
            '0.40 - 0.50: Thảm thực vật dày đặc','0.50 - 0.60: Thảm thực vật dày đặc','0.60 - 0.70: Thảm thực vật dày đặc','0.70 - 1.00: Sử dụng chỉ số NDVI'
            ]

    legend = [{"color": "#" + c, "label": names[i]} for i, c in enumerate(vis["palette"])]

    # Lấy tile URL hợp lệ
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({
        'tile_url': tile_url,
        'legend': legend
    })

def msavi_value():
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    start = request.args.get('start')
    end = request.args.get('end')

    point = ee.Geometry.Point([lon, lat])
    s2Masked = get_sentinel2_value(start, end, point)
    s2Masked = s2Masked.mean()

    s2_img = s2Masked.expression('(2 * NIR + 1 - sqrt((2 * NIR + 1) * (2 * NIR + 1) - 8 * (NIR - RED))) / 2',
        {
            'NIR': s2Masked.select('B8'), 
            'RED': s2Masked.select('B4')
        }).rename('MSAVI')

    value = s2_img.sample(point, scale=10).first().get('MSAVI').getInfo()

    return jsonify({'lat': lat, 'lon': lon, 'msavi': value})

def ndre():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    try:
        if not district:
            shapefile_path = f"demo/commune/hcxa2025_{province}.shp"
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
    s2Masked = get_sentinel2_image(start, end, roi)
    # NDVI
    s2_img = s2Masked.expression ('float ((NIR - REDEDGE) / (NIR + REDEDGE))',{
        'NIR': s2Masked.select ('B8'),  
        'REDEDGE': s2Masked.select ('B5')}).rename('NDRE')

    palette = ['8B0016','B2001F','C50023','DF0029','E54646','EE7C6B','F5A89A',
                    'F3C246','F9CC76','FCE0A6','FFFBD1','E6F1D8','C8E2B1','AFD788',
                    '67BF7F','00AE72','00A06B','008C5E','007F54','006241']

    vis = {
        'min': -1.0,
        'max': 1.0,
        'palette': palette
    }

    map_dict = s2_img.getMapId(vis)

    # Legend labels khớp với palette
        
    names = ['-1.00 - 0.05', '0.05 - 0.10', '0.10 - 0.15','0.15 - 0.20',
            '0.20 - 0.25', '0.25 - 0.30','0.30 - 0.35', '0.35 - 0.40',
            '0.40 - 0.45','0.45 - 0.50','0.50 - 0.55','0.55 - 0.60',
            '0.60 - 0.65','0.65 - 0.70','0.70 - 0.75','0.75 - 0.80',
            '0.80 - 0.85','0.85 - 0.90','0.90 - 0.95','0.95 - 1.00']

    legend = [{"color": "#" + c, "label": names[i]} for i, c in enumerate(vis["palette"])]

    # Lấy tile URL hợp lệ
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({
        'tile_url': tile_url,
        'legend': legend
    })

def ndre_value():
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    start = request.args.get('start')
    end = request.args.get('end')

    point = ee.Geometry.Point([lon, lat])
    s2Masked = get_sentinel2_value(start, end, point)
    s2Masked = s2Masked.mean()

    s2_img = s2Masked.expression ('float ((NIR - REDEDGE) / (NIR + REDEDGE))',{
        'NIR': s2Masked.select ('B8'),  
        'REDEDGE': s2Masked.select ('B5')}).rename('NDRE')

    value = s2_img.sample(point, scale=10).first().get('NDRE').getInfo()

    return jsonify({'lat': lat, 'lon': lon, 'ndre': value})

def ndwi():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    try:
        if not district:
            shapefile_path = f"demo/commune/hcxa2025_{province}.shp"
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
    s2Masked = get_sentinel2_image(start, end, roi)
    # NDWI = (Green - NIR) / (Green + NIR)
    s2_img = s2Masked.expression('float((GREEN - NIR) / (GREEN + NIR))', {
        'GREEN': s2Masked.select('B3'),
        'NIR': s2Masked.select('B8')
    }).rename('NDWI')

    # Bảng màu NDWI — từ đất khô đến nước
    palette = ['8B0016','B2001F','C50023','DF0029','E54646','EE7C6B','F5A89A',
                    'F3C246','F9CC76','FCE0A6','FFFBD1','E6F1D8','C8E2B1','AFD788',
                    '67BF7F','00AE72','00A06B','008C5E','007F54','006241']

    vis = {
        'min': -1.0,
        'max': 1.0,
        'palette': palette
    }

    map_dict = s2_img.getMapId(vis)

    # Các khoảng giá trị NDWI tương ứng
    names = ['-1.00 - 0.05', '0.05 - 0.10', '0.10 - 0.15','0.15 - 0.20',
            '0.20 - 0.25', '0.25 - 0.30','0.30 - 0.35', '0.35 - 0.40',
            '0.40 - 0.45','0.45 - 0.50','0.50 - 0.55','0.55 - 0.60',
            '0.60 - 0.65','0.65 - 0.70','0.70 - 0.75','0.75 - 0.80',
            '0.80 - 0.85','0.85 - 0.90','0.90 - 0.95','0.95 - 1.00']

    legend = [{"color": "#" + c, "label": names[i]} for i, c in enumerate(vis["palette"])]

    # Tạo URL hợp lệ
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({
        'tile_url': tile_url,
        'legend': legend
    })

def ndwi_value():
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    start = request.args.get('start')
    end = request.args.get('end')

    point = ee.Geometry.Point([lon, lat])
    s2Masked = get_sentinel2_value(start, end, point)
    s2Masked = s2Masked.mean()

    s2_img = s2Masked.expression('float((GREEN - NIR) / (GREEN + NIR))', {
        'GREEN': s2Masked.select('B3'),
        'NIR': s2Masked.select('B8')
    }).rename('NDWI')

    value = s2_img.sample(point, scale=10).first().get('NDWI').getInfo()

    return jsonify({'lat': lat, 'lon': lon, 'ndwi': value})

def evi():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    if not district:
        shapefile_path = f"demo/commune/hcxa2025_{province}.shp"
        gdf = gpd.read_file(shapefile_path)
        union_geom = gdf.unary_union
        geom = union_geom.__geo_interface__
        roi = ee.Geometry(geom)
    else :
        roi = get_commune_roi(province, district)
    s2Masked = get_sentinel2_image(start, end, roi)

    # Công thức EVI
    s2_img = s2Masked.expression(
        'float(2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)))',
        {
            'NIR': s2Masked.select('B8'),
            'RED': s2Masked.select('B4'),
            'BLUE': s2Masked.select('B2')
        }
    ).rename('EVI')

    # Bảng màu – từ đất trống (nâu) đến thực vật khỏe (xanh)
    palette = ['8B0016','B2001F','C50023','DF0029','E54646','EE7C6B','F5A89A',
                    'F3C246','F9CC76','FCE0A6','FFFBD1','E6F1D8','C8E2B1','AFD788',
                    '67BF7F','00AE72','00A06B','008C5E','007F54','006241']


    vis = {
        'min': -1.0,
        'max': 1.0,
        'palette': palette
    }

    map_dict = s2_img.getMapId(vis)

    # Legend
    names = ['-1.00 - 0.05', '0.05 - 0.10', '0.10 - 0.15','0.15 - 0.20',
            '0.20 - 0.25', '0.25 - 0.30','0.30 - 0.35', '0.35 - 0.40',
            '0.40 - 0.45','0.45 - 0.50','0.50 - 0.55','0.55 - 0.60',
            '0.60 - 0.65','0.65 - 0.70','0.70 - 0.75','0.75 - 0.80',
            '0.80 - 0.85','0.85 - 0.90','0.90 - 0.95','0.95 - 1.00']
    
    legend = [{"color": "#" + c, "label": names[i]} for i, c in enumerate(vis["palette"])]

    # Xử lý tile URL
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({
        'tile_url': tile_url,
        'legend': legend
    })

def evi_value():
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    start = request.args.get('start')
    end = request.args.get('end')

    point = ee.Geometry.Point([lon, lat])
    s2Masked = get_sentinel2_value(start, end, point)
    s2Masked = s2Masked.mean()

    s2_img = s2Masked.expression(
        'float(2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)))',
        {
            'NIR': s2Masked.select('B8'),
            'RED': s2Masked.select('B4'),
            'BLUE': s2Masked.select('B2')
        }
    ).rename('EVI')

    value = s2_img.sample(point, scale=10).first().get('EVI').getInfo()

    return jsonify({'lat': lat, 'lon': lon, 'evi': value})

def savi():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    if not district:
        shapefile_path = f"demo/commune/hcxa2025_{province}.shp"
        gdf = gpd.read_file(shapefile_path)
        union_geom = gdf.unary_union
        geom = union_geom.__geo_interface__
        roi = ee.Geometry(geom)
    else :
        roi = get_commune_roi(province, district)
    s2Masked = get_sentinel2_image(start, end, roi)

    # Công thức SAVI
    s2_img = s2Masked.expression(
        'float(((NIR - RED) * (1 + L)) / (NIR + RED + L))',
        {
            'NIR': s2Masked.select('B8'),
            'RED': s2Masked.select('B4'),
            'L': 0.5
        }
    ).rename('SAVI')

    # Bảng màu tương tự NDVI nhưng dịu hơn
    palette = ['8B0016','B2001F','C50023','DF0029','E54646','EE7C6B','F5A89A',
                    'F3C246','F9CC76','FCE0A6','FFFBD1','E6F1D8','C8E2B1','AFD788',
                    '67BF7F','00AE72','00A06B','008C5E','007F54','006241']

    vis = {
        'min': -1.0,
        'max': 1.0,
        'palette': palette
    }

    map_dict = s2_img.getMapId(vis)

    # Legend hiển thị giá trị tương ứng với màu
    names = ['-1.00 - 0.05', '0.05 - 0.10', '0.10 - 0.15','0.15 - 0.20',
            '0.20 - 0.25', '0.25 - 0.30','0.30 - 0.35', '0.35 - 0.40',
            '0.40 - 0.45','0.45 - 0.50','0.50 - 0.55','0.55 - 0.60',
            '0.60 - 0.65','0.65 - 0.70','0.70 - 0.75','0.75 - 0.80',
            '0.80 - 0.85','0.85 - 0.90','0.90 - 0.95','0.95 - 1.00']
    
    legend = [{"color": "#" + c, "label": names[i]} for i, c in enumerate(vis["palette"])]

    # Xử lý tile URL
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({
        'tile_url': tile_url,
        'legend': legend
    })

def savi_value():
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    start = request.args.get('start')
    end = request.args.get('end')

    point = ee.Geometry.Point([lon, lat])
    s2Masked = get_sentinel2_value(start, end, point)
    s2Masked = s2Masked.mean()

    s2_img = s2Masked.expression(
        'float(((NIR - RED) * (1 + L)) / (NIR + RED + L))',
        {
            'NIR': s2Masked.select('B8'),
            'RED': s2Masked.select('B4'),
            'L': 0.5
        }
    ).rename('SAVI')

    value = s2_img.sample(point, scale=10).first().get('SAVI').getInfo()

    return jsonify({'lat': lat, 'lon': lon, 'savi': value})

def gndvi():
    start = request.args.get('start')
    end = request.args.get('end')
    province = request.args.get('provinceSelect')
    district = request.args.get('districtSelect')
    if not district:
        shapefile_path = f"demo/commune/hcxa2025_{province}.shp"
        gdf = gpd.read_file(shapefile_path)
        union_geom = gdf.unary_union
        geom = union_geom.__geo_interface__
        roi = ee.Geometry(geom)
    else :
        roi = get_commune_roi(province, district)
    s2Masked = get_sentinel2_image(start, end, roi)

    # Tính GNDVI
    s2_img = s2Masked.expression(
        'float((NIR - GREEN) / (NIR + GREEN))',
        {
            'NIR': s2Masked.select('B8'),
            'GREEN': s2Masked.select('B3')
        }
    ).rename('GNDVI')

    # Bảng màu trực quan hóa tương tự NDVI nhưng xanh hơn
    palette = ['8B0016','B2001F','C50023','DF0029','E54646','EE7C6B','F5A89A',
                    'F3C246','F9CC76','FCE0A6','FFFBD1','E6F1D8','C8E2B1','AFD788',
                    '67BF7F','00AE72','00A06B','008C5E','007F54','006241']

    vis = {
        'min': -1.0,
        'max': 1.0,
        'palette': palette
    }

    map_dict = s2_img.getMapId(vis)

    # Tạo legend tương ứng
    names = ['-1.00 - 0.05', '0.05 - 0.10', '0.10 - 0.15','0.15 - 0.20',
            '0.20 - 0.25', '0.25 - 0.30','0.30 - 0.35', '0.35 - 0.40',
            '0.40 - 0.45','0.45 - 0.50','0.50 - 0.55','0.55 - 0.60',
            '0.60 - 0.65','0.65 - 0.70','0.70 - 0.75','0.75 - 0.80',
            '0.80 - 0.85','0.85 - 0.90','0.90 - 0.95','0.95 - 1.00']
    
    legend = [{"color": "#" + c, "label": names[i]} for i, c in enumerate(vis["palette"])]

    # Kiểm tra tile URL hợp lệ
    if 'tile_fetcher' in map_dict:
        tile_url = map_dict['tile_fetcher'].url_format
    elif 'mapid' in map_dict and 'token' in map_dict:
        tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
    else:
        return jsonify({'error': 'No tile URL available'}), 500

    return jsonify({
        'tile_url': tile_url,
        'legend': legend
    })

def gndvi_value():
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    start = request.args.get('start')
    end = request.args.get('end')

    point = ee.Geometry.Point([lon, lat])
    s2Masked = get_sentinel2_value(start, end, point)
    s2Masked = s2Masked.mean()

    s2_img = s2Masked.expression(
        'float((NIR - GREEN) / (NIR + GREEN))',
        {
            'NIR': s2Masked.select('B8'),
            'GREEN': s2Masked.select('B3')
        }
    ).rename('GNDVI')

    value = s2_img.sample(point, scale=10).first().get('GNDVI').getInfo()

    return jsonify({'lat': lat, 'lon': lon, 'gndvi': value})


