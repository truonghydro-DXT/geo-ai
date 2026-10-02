from datetime import datetime, timedelta
import os
from pathlib import Path

import ee
import geopandas as gpd
from flask import jsonify, request
from shapely.geometry import mapping
from shapely.ops import unary_union

MODULE_DIR = Path(__file__).resolve().parent

DEFAULT_PROVINCE_NAME = 'Tỉnh Nghệ An'
DEFAULT_AREA_FILTER = 0.1
DEFAULT_CLOUD_THRESHOLD = 40
DEFAULT_DELTA_NDVI_THRESHOLD = -0.28
DEFAULT_NDVI_THRESHOLD = 0.59
DEFAULT_BANDS = ['B4', 'B3', 'B2']
STYLE_RESULT_FINAL = {
	'color': "#ff0000",
	'fillColor': "#ff0000",
}


def resolve_commune_shapefile(province):
	candidates = [
		MODULE_DIR.parent / 'commune' / f'hcxa2025_{province}.shp',
		MODULE_DIR.parent.parent / 'product' / 'commune' / f'hcxa2025_{province}.shp',
	]

	for shapefile_path in candidates:
		if shapefile_path.exists():
			return shapefile_path

	return candidates[0]


def _get_request_dates(period=None):
	period = period or request.args.get('period') or request.args.get('timeRange')
	end_value = request.args.get('end') or request.args.get('endValue')
	if end_value:
		days_range = 15
		if period == "month":
			days_range = 30
		elif period == "quarter":
			days_range = 90
		try:
			post_fire_end_dt = datetime.strptime(end_value, '%Y-%m-%d')
		except ValueError:
			raise ValueError('Định dạng end không hợp lệ, dùng YYYY-MM-DD')
		post_fire_end = post_fire_end_dt.strftime('%Y-%m-%d')
		post_fire_start = (post_fire_end_dt - timedelta(days=days_range - 1)).strftime('%Y-%m-%d')
		pre_fire_end = (post_fire_end_dt - timedelta(days=days_range)).strftime('%Y-%m-%d')
		pre_fire_start = (post_fire_end_dt - timedelta(days=(days_range * 2 - 1))).strftime('%Y-%m-%d')
		return pre_fire_start, pre_fire_end, post_fire_start, post_fire_end

	now = datetime.now().date()
	post_fire_end = now.strftime('%Y-%m-%d')
	post_fire_start = (now - timedelta(days=14)).strftime('%Y-%m-%d')
	pre_fire_end = (now - timedelta(days=15)).strftime('%Y-%m-%d')
	pre_fire_start = (now - timedelta(days=30)).strftime('%Y-%m-%d')
	return pre_fire_start, pre_fire_end, post_fire_start, post_fire_end


def get_commune_roi(province, district):
	"""Return (ee.Geometry, error_message). Accepts comma-separated district names."""
	shapefile_path = resolve_commune_shapefile(province)
	if not shapefile_path.exists():
		return None, f"Không tìm thấy shapefile {shapefile_path}"

	gdf = gpd.read_file(shapefile_path)
	if 'tenxa' not in gdf.columns:
		return None, 'Shapefile không có cột tenxa'
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
	geom = mapping(union_geom)
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


def _join_s2_sr_cloud_probability():
	joined = ee.Join.inner().apply(
		primary=ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED'),
		secondary=ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY'),
		condition=ee.Filter.equals(
			leftField='system:index',
			rightField='system:index',
		),
	)

	def _merge_bands(join_result):
		return ee.Image(join_result.get('primary')).addBands(join_result.get('secondary'))

	return ee.ImageCollection(joined.map(_merge_bands))


def _mask_clouds(image):
	cloud_mask = image.select('probability').lt(DEFAULT_CLOUD_THRESHOLD)
	return image.updateMask(cloud_mask)


def _add_area(feature):
	area_ha = feature.geometry().area(0.09).divide(10000)
	return feature.set({
		'area': area_ha,
		'area_ha': area_ha,
	})


def _remove_properties(feature, properties):
	selected = feature.propertyNames().removeAll(ee.List(properties))
	return feature.select(selected)


def _build_vector_download_url(feature_collection):
	try:
		return feature_collection.getDownloadURL('geojson')
	except Exception:
		try:
			return feature_collection.getDownloadURL({'format': 'geojson'})
		except Exception as exc:
			print('vector download error:', str(exc))
			return None


def forerest_loss(period=None):
	province_name = request.args.get('provinceSelect') or DEFAULT_PROVINCE_NAME
	district_name = request.args.get('districtSelect') or request.args.get('district')

	try:
		pre_fire_start, pre_fire_end, post_fire_start, post_fire_end = _get_request_dates(period)
	except ValueError as exc:
		return jsonify({'error': str(exc)}), 400
	
	# === Xác định vùng ROI ===
	gdf, gdf_error = get_commune_gdf(province_name, district_name)
	if gdf_error:
		return jsonify({'error': gdf_error}), 404

	roi, roi_error = get_commune_roi(province_name, district_name)
	if roi_error:
		return jsonify({'error': roi_error}), 404

	if roi is None:
		return jsonify({'error': 'Không xác định được vùng ROI'}), 404

	area_filter = float(request.args.get('areaFilter', DEFAULT_AREA_FILTER))
	delta_ndvi_threshold = float(
		request.args.get('deltaNdviThreshold', DEFAULT_DELTA_NDVI_THRESHOLD)
	)
	ndvi_threshold = float(request.args.get('ndviThreshold', DEFAULT_NDVI_THRESHOLD))

	s2_collection = _join_s2_sr_cloud_probability().filterBounds(roi)
	s2_nearly = s2_collection.filterDate('2017-01-01', datetime.now().strftime('%Y-%m-%d'))

	st2_before = (
		s2_collection.filterDate(pre_fire_start, pre_fire_end)
		.sort('system:time_start', False)
	)
	st2_after = (
		s2_collection.filterDate(post_fire_start, post_fire_end)
		.sort('system:time_start', False)
	)

	st2median_before = st2_before.map(_mask_clouds).mean().clip(roi)
	st2median_after = st2_after.map(_mask_clouds).mean().clip(roi)

	ndvi_before = st2median_before.normalizedDifference(['B8', 'B4']).clip(roi)
	ndvi_after = st2median_after.normalizedDifference(['B8', 'B4']).clip(roi)

	delta_ndvi = ndvi_after.subtract(ndvi_before).clip(roi)
	reclassified = (
		delta_ndvi.where(delta_ndvi.lte(delta_ndvi_threshold), 0)
		.where(delta_ndvi.gt(delta_ndvi_threshold), 1)
	)

	forestloss_vector = reclassified.int().reduceToVectors(
		geometry=roi,
		crs='EPSG:32648',
		scale=30,
		geometryType='polygon',
		eightConnected=False,
		labelProperty='label',
		maxPixels=1e10,
	)

	forest_remove = forestloss_vector.filter(ee.Filter.lt('label', 1))
	forestloss_vector_simplify = forest_remove.map(_add_area)
	forestloss_filter_area = forestloss_vector_simplify.filter(ee.Filter.gt('area', area_filter))

	merge_ndvi = ee.ImageCollection.fromImages([ndvi_before, ndvi_after]).toBands()
	forestloss_mean_ndvi = merge_ndvi.reduceRegions(
		collection=forestloss_filter_area,
		reducer=ee.Reducer.mean(),
		scale=30,
	)

	forestloss_result = forestloss_mean_ndvi.filter(ee.Filter.gt('0_nd', ndvi_threshold))
	forestloss_result = forestloss_result.filter(ee.Filter.lt('1_nd', ndvi_threshold))
	forestloss_result = forestloss_result.map(_add_area)

	vectors = forestloss_result.map(lambda feat: feat.set({'class': 1, 'label': 'change'}))

	largest_feature = ee.Feature(vectors.sort('area_ha', False).first())
	largest_center = None
	largest_area = None

	try:
		largest_center = (
			largest_feature.geometry()
			.centroid(maxError=1)
			.coordinates()
			.getInfo()
		)
		largest_area = largest_feature.get('area_ha').getInfo()
	except Exception as exc:
		print('largest_feature error:', str(exc))

	area_stats = forestloss_result.aggregate_sum('area_ha')
	try:
		area_ha_value = area_stats.getInfo()
	except Exception:
		area_ha_value = None

	area_ha_by_commune = None
	gdf = get_commune_gdf(province_name, district_name)[0]
	if gdf is not None and 'tenxa' in gdf.columns:
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
			commune_area_fc = forestloss_result.geometry().intersection(roi, 1).area(0.09)
			commune_area_fc = ee.FeatureCollection(commune_fc.map(
				lambda feat: feat.set(
					'area_ha',
					ee.Number(forestloss_result.filterBounds(feat.geometry()).geometry().intersection(feat.geometry(), 1).area(0.09)).divide(10000)
				)
			))
			commune_area_info = commune_area_fc.getInfo()
			area_ha_by_commune = []
			for feature in commune_area_info.get('features', []):
				props = feature.get('properties', {})
				area_ha_by_commune.append({
					'tenxa': props.get('tenxa'),
					'area_ha': round(float(props.get('area_ha') or 0), 4)
				})
			area_ha_by_commune.sort(key=lambda item: item['area_ha'], reverse=True)

	map_dict = forestloss_result.style(**STYLE_RESULT_FINAL).getMapId()
	if 'tile_fetcher' in map_dict:
		tile_url = map_dict['tile_fetcher'].url_format
	elif 'mapid' in map_dict and 'token' in map_dict:
		tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
	else:
		tile_url = None

	try:
		latest_range = s2_nearly.reduceColumns(
			ee.Reducer.minMax(),
			['system:time_start'],
		)
		latest_date = ee.Date(latest_range.get('max')).format('YYYY-MM-dd').getInfo()
	except Exception:
		latest_date = None

	vector_download_url = _build_vector_download_url(forestloss_result)

	return jsonify({
		'province': province_name,
		'district': district_name,
		'period': {
			'pre_fire_start': pre_fire_start,
			'pre_fire_end': pre_fire_end,
			'post_fire_start': post_fire_start,
			'post_fire_end': post_fire_end,
		},
		'thresholds': {
			'area_filter': area_filter,
			'delta_ndvi_threshold': delta_ndvi_threshold,
			'ndvi_threshold': ndvi_threshold,
		},
		'latest_date': latest_date,
		'tile_url': tile_url,
		'result_count': forestloss_result.size().getInfo(),
		'download_url': vector_download_url,
		'vector_download_url': vector_download_url,
		'area_ha': area_ha_value,
		'area_ha_by_commune': area_ha_by_commune,
		'largest_patch': {
			'center': largest_center,
			'area_ha': largest_area,
		},
		'style': STYLE_RESULT_FINAL,
	})
