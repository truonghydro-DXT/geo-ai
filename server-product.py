
import ee, json, sys, os, tempfile, importlib, mimetypes, socket, math, io
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file, Response
import psycopg2
import geopandas as gpd
from PIL import Image
import numpy as np
from flask_cors import CORS
from google.auth.exceptions import RefreshError


BASE_DIR = Path(__file__).resolve().parent
RASTERIO_DIR = BASE_DIR / 'venv' / 'Lib' / 'site-packages' / 'rasterio'
if RASTERIO_DIR.exists():
    os.environ['PROJ_LIB'] = str(RASTERIO_DIR / 'proj_data')
    os.environ['PROJ_DATA'] = str(RASTERIO_DIR / 'proj_data')
    os.environ['GDAL_DATA'] = str(RASTERIO_DIR / 'gdal_data')

import rasterio
from rasterio.plot import reshape_as_image


from product.algorithm.image_satellite import sentinel1_api, sentinel2_api, planet_api
from product.algorithm.index_satellite import ndvi, ndvi_value, msavi, msavi_value, ndre, ndre_value, ndwi, ndwi_value
from product.algorithm.index_satellite import evi, evi_value, savi, savi_value, gndvi, gndvi_value
from product.algorithm.zoom import province_bounds
from product.algorithm.forerest_detect import forerest_detect
from product.algorithm.forerest_fire import forerest_fire
from product.algorithm.forest_agb import forerest_agb, forerest_agb_polygon
from product.algorithm.forest_loss import forerest_loss
from product.algorithm.uav_agb import uav_bp


app = Flask(__name__, static_folder='product', static_url_path='')
CORS(app)
app.register_blueprint(uav_bp)

SERVICE_ACCOUNT_JSON = BASE_DIR / 'gee-service-account.json'
COMMUNE_DIRS = [
    BASE_DIR / 'product' / 'commune',
    BASE_DIR / 'product' / 'commune',
]

if not SERVICE_ACCOUNT_JSON.exists():
    raise FileNotFoundError(f'Missing service account file: {SERVICE_ACCOUNT_JSON}')

with SERVICE_ACCOUNT_JSON.open('r', encoding='utf8') as f:
    sa = json.load(f)

SERVICE_ACCOUNT_EMAIL = sa['client_email']
KEY_PATH = str(SERVICE_ACCOUNT_JSON)

credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT_EMAIL, KEY_PATH)
EE_READY = False
EE_INIT_ERROR = None

try:
    ee.Initialize(credentials)
    EE_READY = True
except RefreshError as exc:
    EE_INIT_ERROR = str(exc)
    print(
        'Earth Engine service-account login failed. '\
        'Check system time synchronization and confirm the service-account key is valid.'
    )
    print(EE_INIT_ERROR)

EE_ROUTES = {
    '/sentinel1',
    '/sentinel2',
    '/planet',
    '/ndvi',
    '/ndvi_value',
    '/msavi',
    '/msavi_value',
    '/ndre',
    '/ndre_value',
    '/ndwi',
    '/ndwi_value',
    '/evi',
    '/evi_value',
    '/savi',
    '/savi_value',
    '/gndvi',
    '/gndvi_value',
    '/forerest_detect',
    '/forerest_loss',
    '/forerest_agb',
    '/forerest_agb_polygon',
}


def _wants_json_error():
    path = request.path or ''
    return (
        path in EE_ROUTES
        or path.startswith('/forerest_')
        or path.startswith('/uav/api')
        or path.startswith('/load-district')
        or request.accept_mimetypes.best == 'application/json'
        or request.method in ('POST', 'PUT', 'PATCH')
    )


@app.before_request
def guard_earth_engine_routes():
    if request.path in EE_ROUTES and not EE_READY:
        return jsonify({
            'success': False,
            'message': 'Earth Engine is not initialized.',
            'details': EE_INIT_ERROR,
        }), 503


@app.errorhandler(404)
def json_not_found(error):
    if _wants_json_error():
        return jsonify({'error': f'Không tìm thấy API {request.path}'}), 404
    return error.get_response()


@app.errorhandler(405)
def json_method_not_allowed(error):
    if _wants_json_error():
        return jsonify({
            'error': f'{request.method} {request.path} không được hỗ trợ. Khởi động lại server nếu vừa thêm API.',
        }), 405
    return error.get_response()


logged_in_users = {}


def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        sock.close()


def resolve_commune_shapefile(province):
    for commune_dir in COMMUNE_DIRS:
        shapefile_path = commune_dir / f'hcxa2025_{province}.shp'
        if shapefile_path.exists():
            return shapefile_path
    return COMMUNE_DIRS[0] / f'hcxa2025_{province}.shp'


def tile_bounds_3857(z, x, y):
    initial_resolution = 2 * math.pi * 6378137 / 256
    origin_shift = 2 * math.pi * 6378137 / 2.0
    resolution = initial_resolution / (2 ** z)
    minx = x * 256 * resolution - origin_shift
    maxx = (x + 1) * 256 * resolution - origin_shift
    maxy = origin_shift - y * 256 * resolution
    miny = origin_shift - (y + 1) * 256 * resolution
    return minx, miny, maxx, maxy

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    conn = psycopg2.connect(
        user='postgres',
        host='localhost',
        database='datasystem',
        password='lifetex@DXT9385',
        port=5662
    )

    cur = conn.cursor()
    query = """
        SELECT permission, project_id 
        FROM user_table 
        WHERE user_name = %s AND password = %s
    """
    cur.execute(query, (username, password))
    rows = cur.fetchall()

    if rows:
        permission = rows[0][0]
        project_ids = [r[1] for r in rows]
        result = {"success": True, "permission": permission, "projectIds": project_ids}
    else:
        result = {"success": False, "message": "Invalid username or password"}

    cur.close()
    conn.close()
    return jsonify(result)

@app.route('/update-login-status', methods=['POST'])
def update_login_status():
    data = request.get_json()
    username = data.get("username")
    status = data.get("status")

    if not username or not status:
        return jsonify({"success": False, "message": "Missing username or status"}), 400

    if status == 'online':
        logged_in_users[username] = True
    else:
        logged_in_users.pop(username, None)

    return jsonify({"success": True, "message": "Status updated"})


@app.route('/get-logged-in-users', methods=['GET'])
def get_logged_in_users():
    return jsonify(list(logged_in_users.keys()))


@app.route('/load-user', methods=['GET'])
def load_user():
    table_name = request.args.get('table')
    project_id = request.args.get('project_id')

    if not table_name or not project_id:
        return jsonify({"success": False, "message": "Table name and Project ID are required."}), 400

    try:
        conn = psycopg2.connect(
            user='postgres',
            host='localhost',
            database='datasystem',
            password='lifetex@DXT9385',
            port=5662
        )
        cur = conn.cursor()

        query = f"SELECT account_name, fullname FROM {table_name} WHERE project_id = %s"
        cur.execute(query, (project_id,))
        rows = cur.fetchall()
        users = [{"account_name": r[0], "fullname": r[1]} for r in rows]

        cur.close()
        conn.close()

        return jsonify(users)
    except Exception as e:
        print("Database query error:", e)
        return jsonify({"success": False, "message": "Internal server error"}), 500
    

@app.route('/')
def index():
    return send_from_directory('product', 'index.html')

@app.route('/load-districts', methods=['GET'])
def load_districts():
    province = request.args.get('provinceSelect')
    if not province:
        return jsonify({'error': 'Thiếu provinceSelect'}), 400

    shapefile_path = resolve_commune_shapefile(province)
    if not shapefile_path.exists():
        return jsonify({'error': f'Không tìm thấy {shapefile_path}'}), 404

    try:
        gdf = gpd.read_file(shapefile_path)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        # Trả về GeoJSON đúng định dạng
        geojson_str = gdf.to_json()
        return Response(geojson_str, content_type='application/json')
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/load-district-geometry', methods=['GET'])
def load_district_geometry():
    province = request.args.get('provinceSelect')
    district_values = request.args.getlist('districtSelect')
    if len(district_values) == 1 and ',' in district_values[0]:
        district_values = district_values[0].split(',')
    districts = [district.strip() for district in district_values if district and district.strip()]

    if not province or not districts:
        return jsonify({'error': 'Thiếu provinceSelect hoặc districtSelect'}), 400

    shapefile_path = resolve_commune_shapefile(province)
    if not shapefile_path.exists():
        return jsonify({'error': f'Không tìm thấy shapefile {shapefile_path}'}), 404

    try:
        gdf = gpd.read_file(shapefile_path)

        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        district_lookup = {district.lower().strip() for district in districts}
        gdf_filtered = gdf[gdf["tenxa"].str.lower().str.strip().isin(district_lookup)]

        if gdf_filtered.empty:
            return jsonify({'error': f'Không tìm thấy xã/phường "{", ".join(districts)}" trong {province}'}), 404

        # ✅ Tính bbox (minx, miny, maxx, maxy)
        minx, miny, maxx, maxy = gdf_filtered.total_bounds

        # ✅ Chuyển sang GeoJSON
        geojson = json.loads(gdf_filtered.to_json())

        # ✅ Gắn bbox vào kết quả trả về
        geojson["bbox"] = {
            "minx": minx,
            "miny": miny,
            "maxx": maxx,
            "maxy": maxy
        }

        return jsonify(geojson)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    
@app.route('/sentinel1')
def sentinel1_route():
    return sentinel1_api()

@app.route('/sentinel2')
def sentinel2_route():
    return sentinel2_api()

@app.route('/planet', methods=["GET"])
def planet_route():
    return planet_api()

@app.route('/ndvi')
def ndvi_route():
    return ndvi()

@app.route('/ndvi_value')
def ndvi_value_route():
    return ndvi_value()


@app.route('/quyhoach-tiles/<int:z>/<int:x>/<int:y>.png')
def quyhoach_tile(z, x, y):
    vrt_path = BASE_DIR / 'product' / 'raster' / 'tinhnghean' / 'kyson-nghean.vrt'
    if not vrt_path.exists():
        return jsonify({'error': f'Không tìm thấy file {vrt_path}'}), 404

    try:
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds

        minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)

        with rasterio.open(vrt_path) as src:
            if src.crs and src.crs.to_epsg() not in (None, 3857):
                print(f'Warning: quyhoach raster CRS is {src.crs}, serving tile via source transform anyway')

            window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
            window = window.round_offsets().round_lengths()

            data = src.read(
                indexes=[1, 2, 3, 4],
                window=window,
                out_shape=(4, 256, 256),
                resampling=Resampling.nearest,
                boundless=True,
                fill_value=0,
            )

        if data.shape[0] == 4:
            rgba = np.moveaxis(data, 0, -1)
        else:
            rgb = np.moveaxis(data[:3], 0, -1)
            alpha = np.full((256, 256, 1), 255, dtype=np.uint8)
            rgba = np.concatenate([rgb, alpha], axis=-1)

        rgba = np.clip(rgba, 0, 255).astype(np.uint8)
        image = Image.fromarray(rgba, mode='RGBA')

        buffer = io.BytesIO()
        image.save(buffer, format='PNG', optimize=False)
        buffer.seek(0)
        return Response(buffer.getvalue(), mimetype='image/png')

    except Exception as exc:
        print('quyhoach_tile error:', exc)
        return jsonify({'error': str(exc)}), 500

@app.route('/msavi')
def msavi_route():
    return msavi()

@app.route('/msavi_value')
def msavi_value_route():
    return msavi_value()

@app.route('/ndre')
def ndre_route():
    return ndre()

@app.route('/ndre_value')
def ndre_value_route():
    return ndre_value()

@app.route('/ndwi')
def ndwi_route():
    return ndwi()

@app.route('/ndwi_value')
def ndwi_value_route():
    return ndwi_value()

@app.route('/evi')
def evi_route():
    return evi()

@app.route('/evi_value')
def evi_value_route():
    return evi_value()

@app.route('/savi')
def savi_route():
    return savi()

@app.route('/savi_value')
def savi_value_route():
    return savi_value()

@app.route('/gndvi')
def gndvi_route():
    return gndvi()

@app.route('/gndvi_value')
def gndvi_value_route():
    return gndvi_value()

@app.route('/province')
def province_route():
    return province_bounds()

@app.route('/forerest_detect')
def forerest_detect_route():
    return forerest_detect()

@app.route('/forerest_fire')
def forerest_fire_route():
    return forerest_fire()


@app.route('/forerest_agb')
def forerest_agb_route():
    return forerest_agb()


@app.route('/forerest_agb_polygon', methods=['GET', 'POST'])
def forerest_agb_polygon_route():
    if request.method != 'POST':
        return jsonify({'error': 'Dùng POST với coordinates'}), 405
    return forerest_agb_polygon()


@app.route('/forerest_loss')
def forerest_loss_route():
    return forerest_loss(request.args.get('period'))

@app.route('/modules')
def get_modules():
    # Trả về danh sách module với value và label hiển thị
    modules = [
        {"value": "change_detection", "label": "Phát hiện biến động"},
        {"value": "classify", "label": "Phân loại đối tượng"},
        {"value": "sam", "label": "Phân đoạn hình ảnh"},
        {"value": "segmentation", "label": "Phân vùng đối tượng"}
    ]
    return jsonify(modules)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3300))
    local_ip = get_local_ip()
    print(f'Server available at http://{local_ip}:{port}')
    print(f'Local access: http://127.0.0.1:{port}')
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)

# @app.route('/process', methods=['POST'])
# def process_image():
#     ai_type = request.form.get("aiType", "GeoAI")

#     file = request.files.get("image")
#     if not file:
#         return jsonify({"success": False, "message": "Missing image"}), 400

#     tmp_dir = tempfile.gettempdir()
#     tmp_path = os.path.join(tmp_dir, file.filename)
#     file.save(tmp_path)

#     if ai_type == "TorchGeo":
#         try:
#             import torch
#             from torchvision import models
#             from PIL import Image
#             import numpy as np
#             import rasterio
#             from rasterio.transform import Affine, from_bounds
#             from rasterio.enums import Resampling

#             model_name = request.form.get("torchModel", "FCN_ResNet50")
#             num_classes = int(request.form.get("numClasses", 5))

#             if model_name == "FCN_ResNet50":
#                 model = models.segmentation.fcn_resnet50(weights="DEFAULT")
#                 model.classifier[4] = torch.nn.Conv2d(512, num_classes, kernel_size=1)
#             elif model_name == "FCN_ResNet101":
#                 model = models.segmentation.fcn_resnet101(weights="DEFAULT")
#                 model.classifier[4] = torch.nn.Conv2d(512, num_classes, kernel_size=1)
#             elif model_name == "DeepLabV3_ResNet50":
#                 model = models.segmentation.deeplabv3_resnet50(weights="DEFAULT")
#                 model.classifier[4] = torch.nn.Conv2d(256, num_classes, kernel_size=1)
#             elif model_name == "DeepLabV3_ResNet101":
#                 model = models.segmentation.deeplabv3_resnet101(weights="DEFAULT")
#                 model.classifier[4] = torch.nn.Conv2d(256, num_classes, kernel_size=1)
#             elif model_name == "LRASPP_MobileNetV3_Large":
#                 model = models.segmentation.lraspp_mobilenet_v3_large(weights="DEFAULT")
#                 model.classifier.low_classifier = torch.nn.Conv2d(40, num_classes, kernel_size=1)
#                 model.classifier.high_classifier = torch.nn.Conv2d(128, num_classes, kernel_size=1)
#             else:
#                 return jsonify({"success": False, "message": f"Unknown model: {model_name}"}), 400

#             model.eval()

#             img = Image.open(tmp_path).convert("RGB")
#             arr = np.array(img)
#             height, width = arr.shape[:2]
#             tensor = torch.from_numpy(arr.transpose(2,0,1)).unsqueeze(0).float()/255.0

#             with torch.no_grad():
#                 out = model(tensor)
#                 if isinstance(out, dict) and "out" in out:
#                     pred = out["out"][0].argmax(0).numpy()
#                 elif isinstance(out, torch.Tensor):
#                     pred = out[0].argmax(0).numpy()
#                 else:
#                     pred = np.zeros((height, width))

#             # Lưu dưới dạng GeoTIFF
#             result_path = os.path.join(tmp_dir, f"TorchGeo_{model_name}.tif")

#             # Gán hệ tọa độ và bounds theo file đầu vào nếu là GeoTIFF
#             crs = 'EPSG:4326'
#             transform = Affine(1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
#             if tmp_path.lower().endswith((".tif", ".tiff")):
#                 try:
#                     with rasterio.open(tmp_path) as src:
#                         crs = src.crs or crs
#                         minx, miny, maxx, maxy = src.bounds
#                         transform = from_bounds(minx, miny, maxx, maxy, width, height)
#                 except:
#                     pass  # Sử dụng mặc định nếu không đọc được

#             with rasterio.open(
#                 result_path, 'w',
#                 driver='GTiff',
#                 height=height,
#                 width=width,
#                 count=1,
#                 dtype='uint8',
#                 crs=crs,
#                 transform=transform
#             ) as dst:
#                 dst.write(pred.astype('uint8'), 1)

#             return jsonify({"success": True, "result": f"/uploads/{os.path.basename(result_path)}"})

#         except Exception as e:
#             return jsonify({"success": False, "message": str(e)}), 500

#     else:
#         module_name = request.form.get("module")
#         if not module_name:
#             return jsonify({"success": False, "message": "Missing module"}), 400
#         if module_name == 'change_detection':
#             file1 = request.files.get('image1')
#             file2 = request.files.get('image2')
#             if not file1 or not file2:
#                 return jsonify({
#                     "success": False,
#                     "message": "Change detection requires two images (image1 and image2)"
#                 }), 400

#             tmp_dir = tempfile.gettempdir()
#             tmp1_path = os.path.join(tmp_dir, file1.filename)
#             tmp2_path = os.path.join(tmp_dir, file2.filename)
#             file1.save(tmp1_path)
#             file2.save(tmp2_path)
#             input_paths = (tmp1_path, tmp2_path)

#             src_meta = None
#             if tmp1_path.lower().endswith((".tif", ".tiff")):
#                 with rasterio.open(tmp1_path) as src:
#                     src_meta = src.meta.copy()

#         else:  
#             file = request.files.get('image')
#             if not file:
#                 return jsonify({"success": False, "message": "Missing image"}), 400

#             tmp_dir = tempfile.gettempdir()
#             tmp_path = os.path.join(tmp_dir, file.filename)
#             file.save(tmp_path)
#             input_paths = tmp_path

#             src_meta = None
#             if tmp_path.lower().endswith((".tif", ".tiff")):
#                 with rasterio.open(tmp_path) as src:
#                     src_meta = src.meta.copy()
#         try:
#             module = importlib.import_module(f"geoai.{module_name}")
#             if not hasattr(module, 'process'):
#                 return jsonify({"success": False, "message": "Module không có hàm process()."}), 400

#             # Gọi hàm process
#             result = module.process(input_paths)

#             # Nếu trả về numpy array → lưu dưới dạng GeoTIFF
#             if isinstance(result, np.ndarray):
#                 height, width = result.shape[:2]
#                 out_tmp_path = os.path.join(tmp_dir, f"{module_name}_result.tif")

#                 # Gán hệ tọa độ và bounds theo file đầu vào nếu là GeoTIFF
#                 crs = 'EPSG:4326'
#                 transform = Affine(1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
#                 input_file_path = tmp1_path if module_name == 'change_detection' else tmp_path
#                 if input_file_path.lower().endswith((".tif", ".tiff")):
#                     try:
#                         with rasterio.open(input_file_path) as src:
#                             crs = src.crs or crs
#                             minx, miny, maxx, maxy = src.bounds
#                             transform = from_bounds(minx, miny, maxx, maxy, width, height)
#                     except:
#                         pass  # Sử dụng mặc định nếu không đọc được

#                 with rasterio.open(
#                     out_tmp_path, 'w',
#                     driver='GTiff',
#                     height=height,
#                     width=width,
#                     count=1,
#                     dtype='uint8',
#                     crs=crs,
#                     transform=transform
#                 ) as dst:
#                     dst.write(result.astype('uint8'), 1)
#                 return jsonify({"success": True, "result": f"/uploads/{os.path.basename(out_tmp_path)}"})

#             # Nếu trả về path ảnh
#             elif isinstance(result, str) and os.path.exists(result):
#                 return jsonify({"success": True, "result": result})

#             else:
#                 return jsonify({"success": False, "message": "Module không trả về ảnh hợp lệ."})

#         except Exception as e:
#             return jsonify({"success": False, "message": str(e)}), 500


# @app.route('/uploads/<filename>') 
# def uploaded_file(filename): 
#     return send_from_directory(tempfile.gettempdir(), filename)


