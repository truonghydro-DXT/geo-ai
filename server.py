
import ee, json, sys, os, tempfile, importlib, mimetypes, socket
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file, Response
import psycopg2
import geopandas as gpd
import rasterio
from rasterio.plot import reshape_as_image
from PIL import Image
import numpy as np
from flask_cors import CORS
from google.auth.exceptions import RefreshError


from public.algorithm.image_satellite import sentinel1_api, sentinel2_api, planet_api
from public.algorithm.index_satellite import ndvi, ndvi_value, msavi, msavi_value, ndre, ndre_value, ndwi, ndwi_value
from public.algorithm.index_satellite import evi, evi_value, savi, savi_value, gndvi, gndvi_value
from public.algorithm.build_detect import build_detect
from public.algorithm.change_lulc import landuser_layers
from public.algorithm.zoom import province_bounds
from public.algorithm.flood_map import flood_area
from public.algorithm.drought_map import drought_area
from public.algorithm.agri_app import agri_layer
from public.algorithm.landside import landslide_area
from public.algorithm.forerest_detect import forerest_detect
from public.algorithm.forerest_fire import forerest_fire
from public.algorithm.forest_agb import forerest_agb, forerest_agb_polygon
from public.algorithm.uav_agb import uav_bp


app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)
app.register_blueprint(uav_bp)

BASE_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_JSON = BASE_DIR / 'gee-service-account.json'

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
    '/landslide_area',
    '/forerest_fire',
    '/forerest_agb',
    '/forerest_agb_polygon',
}


@app.before_request
def guard_earth_engine_routes():
    if request.path in EE_ROUTES and not EE_READY:
        return jsonify({
            'success': False,
            'message': 'Earth Engine is not initialized.',
            'details': EE_INIT_ERROR,
        }), 503


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
    return send_from_directory('public', 'index.html')

@app.route('/load-districts', methods=['GET'])
def load_districts():
    province = request.args.get('provinceSelect')
    if not province:
        return jsonify({'error': 'Thiếu provinceSelect'}), 400

    shapefile_path = f"public/commune/hcxa2025_{province}.shp"
    if not os.path.exists(shapefile_path):
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

    shapefile_path = f"public/commune/hcxa2025_{province}.shp"
    if not os.path.exists(shapefile_path):
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

@app.route('/build_detect')
def build_detect_route():
    return build_detect()

@app.route('/flood_area')
def flood_area_route():
    return flood_area()

@app.route('/drought_area')
def drought_area_route():
    return drought_area()


@app.route('/landslide_area')
def landslide_area_route():
    return landslide_area()


@app.route('/landuser_layer')
def landuser_layers_route():
    return landuser_layers()

@app.route('/agrir_layer')
def agrir_layer_route():
    return agri_layer()

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
    port = int(os.getenv('PORT', 2000))
    local_ip = get_local_ip()
    print(f'Server available at http://{local_ip}:{port}')
    print(f'Local access: http://127.0.0.1:{port}')
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
