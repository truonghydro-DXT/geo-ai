"""Python port of the ALDI landslide detection script.

This module mirrors the core computation in
``public/mapshow/landside.js`` and exposes a Python entry point that
returns the main Earth Engine layers.
"""

from __future__ import annotations

import os

import ee
import geopandas as gpd
from flask import request, jsonify


N_MONTHS = 12

NDSI_THRESH_VALUES = [
	0.24, 0.25, 0.28, 0.29, 0.29, 0.37, 0.31, 0.19, 0.78, 0.37,
	0.12, 0.13, 0.10, 0.15, 0.11, 0.11, 0.09, 0.19, 0.15, 0.26,
	0.90, 0.78, 0.84, 0.82, 0.92, 0.64, 0.79, 0.59, 0.60, 0.75,
	0.92, 0.60, 0.85, 0.90, 0.97, 0.78, 0.84, 0.53, 0.57, 0.92,
	0.48, 0.82, 0.37, 0.36, 0.35, 0.83, 0.51, 0.60, 0.73, 0.99,
	0.32, 0.34, 0.23, 0.68, 0.36, 0.76, 0.24, 0.45, 0.92, 0.44,
	0.71, 0.16, 0.59, 0.70, 0.16, 0.51, 0.84, 0.44, 0.84, 0.27,
	0.71, 0.16, 0.16, 0.59, 0.51, 0.70, 0.27, 0.44, 0.11, 0.50,
	0.94, 0.24, 0.62, 0.20, 0.69, 0.68, 0.18, 0.67, 0.71, 0.67,
	0.94, 0.68, 0.24, 0.69, 0.67, 0.62, 0.31, 0.20, 0.61, 0.88,
]

ALPHA_VALUES = [
	1.58, 5.12, 5.97, 6.93, 4.41, 0.42, 8.38, 7.68, 4.94, 4.45,
	5.04, 2.89, 9.57, 5.88, 8.12, 0.97, 7.72, 7.68, 3.86, 2.87,
	9.17, 5.93, 6.07, 6.36, 9.23, 0.01, 5.44, 3.23, 0.46, 8.79,
	9.23, 0.46, 6.52, 9.17, 5.39, 5.93, 6.07, 4.65, 9.44, 1.73,
	1.48, 4.35, 1.19, 6.05, 1.50, 5.57, 9.73, 7.17, 1.46, 7.89,
	3.95, 5.82, 0.65, 1.47, 6.05, 2.30, 9.10, 6.86, 1.26, 8.03,
	0.50, 7.16, 2.12, 9.75, 5.07, 5.18, 9.70, 6.91, 3.62, 6.37,
	0.50, 5.07, 7.16, 2.12, 5.18, 9.75, 6.37, 6.91, 9.77, 2.15,
	7.78, 1.59, 5.60, 4.07, 4.84, 7.07, 2.00, 9.32, 9.39, 6.41,
	7.78, 7.07, 1.59, 4.84, 9.32, 5.60, 2.59, 4.07, 5.54, 7.98,
]

AB_RATIO_VALUES = [
	77.23, 35.45, 66.09, 88.90, 33.12, 66.48, 58.71, 38.84, 39.59, 22.26,
	67.94, 13.82, 30.81, 24.94, 15.51, 46.67, 29.55, 38.84, 8.75, 31.64,
	2.50, 2.42, 2.47, 1.94, 2.62, 2.21, 4.55, 3.15, 2.34, 1.48,
	2.62, 2.34, 2.20, 2.50, 3.98, 2.42, 2.47, 3.15, 4.82, 1.59,
	3.07, 2.99, 4.08, 2.71, 4.39, 3.93, 3.03, 2.95, 2.54, 4.60,
	2.38, 1.49, 2.44, 1.68, 2.71, 1.47, 1.23, 2.03, 1.99, 1.64,
	76.51, 33.43, 90.03, 38.26, 85.32, 73.51, 11.00, 37.10, 8.30, 28.02,
	76.51, 85.32, 33.43, 90.03, 73.51, 38.26, 28.02, 37.10, 41.00, 21.40,
	81.97, 0.03, 0.09, 0.02, 15.50, 1.39, 16.35, 7.18, 3.46, 48.11,
	81.97, 1.39, 0.03, 15.50, 7.18, 0.09, 0.02, 0.02, 2.85, 1.09,
]

AL_RATIO_VALUES = [
	0.029, 0.051, 0.021, 0.049, 0.017, 0.032, 0.051, 0.048, 0.026, 0.033,
	0.045, 0.022, 0.067, 0.013, 0.015, 0.103, 0.021, 0.048, 0.017, 0.011,
	0.054, 0.046, 0.042, 0.033, 0.099, 0.027, 0.032, 0.026, 0.108, 0.024,
	0.099, 0.108, 0.182, 0.054, 0.173, 0.046, 0.042, 0.293, 0.143, 0.056,
	0.161, 0.168, 0.201, 0.217, 0.236, 0.319, 0.343, 0.357, 0.067, 0.168,
	0.373, 0.104, 1.163, 0.244, 0.217, 0.138, 0.146, 0.107, 0.540, 0.413,
	0.010, 0.010, 0.012, 0.012, 0.011, 0.013, 0.012, 0.013, 0.011, 0.012,
	0.010, 0.011, 0.010, 0.012, 0.013, 0.012, 0.012, 0.013, 0.014, 0.014,
	3.460, 1.159, 0.015, 0.072, 0.016, 15.861, 0.170, 0.033, 0.337, 0.027,
	3.460, 15.861, 1.159, 0.016, 0.033, 0.015, 0.011, 0.072, 72.011, 1.188,
]

GAUSS_C_SUM = sum([
	0.000124818987,
	-0.001075204047,
	0.005198775019,
	-0.019198292004,
	0.059054035642,
	-0.151968751364,
	0.319152932694,
	-0.531923007300,
	0.797884560593,
])

GAUSS_C2_SUM = sum([
	-0.000045255659,
	0.000152529290,
	-0.000019538132,
	-0.000676904986,
	0.001390604284,
	-0.000794620820,
	-0.002034254874,
	0.006549791214,
	-0.010557625006,
	0.011630447319,
	-0.009279453341,
	0.005353579108,
	-0.002141268741,
	0.000535310849,
	0.999936657524,
])


def _as_date(value):
	return value if isinstance(value, ee.Date) else ee.Date(value)


def get_commune_roi(province, district):
	shapefile_path = f"public/commune/hcxa2025_{province}.shp"
	if not os.path.exists(shapefile_path):
		raise ValueError(f"Shapefile not found: {shapefile_path}")

	gdf = gpd.read_file(shapefile_path)
	if "tenxa" not in gdf.columns:
		raise ValueError("Shapefile không có cột tenxa")

	if district and str(district).strip():
		gdf["tenxa_norm"] = gdf["tenxa"].astype(str).str.lower().str.strip()
		if isinstance(district, str) and "," in district:
			parts = [part.strip().lower() for part in district.split(",") if part.strip()]
		elif isinstance(district, (list, tuple)):
			parts = [str(item).strip().lower() for item in district if str(item).strip()]
		else:
			parts = [str(district).strip().lower()]

		if not parts:
			raise ValueError("Empty district selection")

		gdf = gdf[gdf["tenxa_norm"].isin(parts)]
		if gdf.empty:
			raise ValueError(f'Không tìm thấy xã/phường "{district}" trong {province}')

	union_geom = gdf.unary_union
	if union_geom.is_empty:
		raise ValueError(f'Không tìm thấy hình học hợp lệ cho xã/phường "{district}" trong {province}')
	if not union_geom.is_valid:
		union_geom = union_geom.buffer(0)
	return ee.Geometry(union_geom.__geo_interface__)


def f_gauss(z):
	"""ACM Algorithm #209 approximation of the standard normal CDF."""
	y = z.abs().divide(2)
	w = y.multiply(y)
	y2 = y.subtract(2.0)

	p1 = ee.Image.constant(GAUSS_C_SUM).multiply(w.pow(9)).multiply(y).multiply(2.0)
	p2 = ee.Image.constant(GAUSS_C2_SUM).multiply(y2.pow(15))

	p = z.expression(
		'z == 0 ? 0.0 : y >= 3 ? 1 : y < 1 ? p1 : p2',
		{'z': z, 'y': y, 'p1': p1, 'p2': p2},
	)
	return p.expression(
		'z == 0 ? 0.5 : z > 0 ? (1 + p) / 2 : (1 - p) / 2',
		{'z': z, 'p': p},
	)


def f_student(t, df):
	"""ACM Algorithm #395 student-t tail probability."""
	tsq = t.multiply(t)
	y = tsq.divide(df)
	b = y.add(1.0)
	lnb = b.log()
	my_y0 = y.expression('y > 0.000001 ? lnb : y', {'y': y, 'lnb': lnb})
	a = df.subtract(0.5)
	bn = a.multiply(a).multiply(48)
	yn = my_y0.multiply(a)
	sqrt_yn = yn.sqrt()
	y2 = yn.expression(
		'(((((-0.4 * yn - 3.3) * yn - 24.0) * yn - 85.5) / (0.8 * yn * yn + 100.0 + bn) + yn + 3.0) / bn + 1.0) * sqrtY',
		{'yn': yn, 'bn': bn, 'sqrtY': sqrt_yn},
	)
	return f_gauss(y2.multiply(-1)).multiply(2)


def f_add_ndvi_l8(image):
	return image.addBands(image.normalizedDifference(['B5', 'B4']).rename('nd'))


def f_add_ndvi_l457(image):
	return image.addBands(image.normalizedDifference(['B4', 'B3']).rename('nd'))


def f_add_ndsi_l8(image):
	ndsi = image.expression(
		'(GREEN - SWIR) / (GREEN + SWIR)',
		{'GREEN': image.select('B3'), 'SWIR': image.select('B6')},
	)
	return image.addBands(ndsi.rename('ndsi'))


def f_add_ndsi_l457(image):
	ndsi = image.expression(
		'(GREEN - SWIR) / (GREEN + SWIR)',
		{'GREEN': image.select('B2'), 'SWIR': image.select('B5')},
	)
	return image.addBands(ndsi.rename('ndsi'))


def _empty_stack_stats(land_mask):
	return ee.Image.constant([0, 0]).rename(['nd', 'ndsi_median']).updateMask(land_mask)


def f_cloud_mask(image, cloud_thresh=50):
	clouds = ee.Algorithms.Landsat.simpleCloudScore(image).select(['cloud'])
	return image.updateMask(clouds.lt(cloud_thresh))


def f_pan_sharpen_l8(image):
	rgb = image.select('B5', 'B4', 'B3')
	pan = image.select('B8')
	huesat = rgb.rgbToHsv().select('hue', 'saturation')
	upres = ee.Image.cat(huesat, pan).hsvToRgb()
	return image.addBands(upres)


def f_pan_sharpen_l7(image):
	rgb = image.select('B4', 'B3', 'B2')
	pan = image.select('B8')
	huesat = rgb.rgbToHsv().select('hue', 'saturation')
	upres = ee.Image.cat(huesat, pan).hsvToRgb()
	return image.addBands(upres)


def f_stack_stats(start_doy, end_doy, start_yr, end_yr, aoi):
	"""Calculate monthly NDVI/NDSI statistics for the AOI."""
	land_mask = ee.Image('CGIAR/SRTM90_V4').mask()

	l8_coll = (
		ee.ImageCollection('LANDSAT/LC08/C02/T1')
		.filterBounds(aoi)
		.filterDate(start_yr, end_yr)
		.filter(ee.Filter.calendarRange(start_doy, end_doy, 'day_of_year'))
		.sort('CLOUD_COVER')
		.map(f_add_ndvi_l8)
		.map(f_add_ndsi_l8)
		.map(f_cloud_mask)
	)
	l7_coll = (
		ee.ImageCollection('LANDSAT/LC08/C02/T1')
		.filterBounds(aoi)
		.filterDate(start_yr, end_yr)
		.filter(ee.Filter.calendarRange(start_doy, end_doy, 'day_of_year'))
		.map(f_add_ndvi_l457)
		.map(f_add_ndsi_l457)
		.map(f_cloud_mask)
	)
	l5_coll = (
		ee.ImageCollection('LANDSAT/LE07/C02/T1')
		.filterBounds(aoi)
		.filterDate(start_yr, end_yr)
		.filter(ee.Filter.calendarRange(start_doy, end_doy, 'day_of_year'))
		.map(f_add_ndvi_l457)
		.map(f_add_ndsi_l457)
		.map(f_cloud_mask)
	)

	ndvi_coll = ee.ImageCollection(
		l5_coll.select('nd').merge(l7_coll.select('nd')).merge(l8_coll.select('nd'))
	)
	ndsi_coll = ee.ImageCollection(
		l5_coll.select('ndsi').merge(l7_coll.select('ndsi')).merge(l8_coll.select('ndsi'))
	)

	if ndvi_coll.size().getInfo() == 0 or ndsi_coll.size().getInfo() == 0:
		return _empty_stack_stats(land_mask)

	ndvi_median = ndvi_coll.median()
	ndsi_median = ndsi_coll.reduce(ee.Reducer.median())
	if ndvi_median.bandNames().size().getInfo() == 0 or ndsi_median.bandNames().size().getInfo() == 0:
		return _empty_stack_stats(land_mask)
	return ndvi_median.addBands(ndsi_median).unmask(0).updateMask(land_mask)


def landslide_aldi(trig_t1, trig_t2, aoi):
	"""Compute the ALDI landslide layers for a region and trigger dates."""
	trig_t1 = _as_date(trig_t1)
	trig_t2 = _as_date(trig_t2)
	aoi = ee.Geometry(aoi)

	start_yr_t1 = trig_t1.advance(-5, 'years')
	end_yr_t2 = trig_t2.advance(2, 'years')

	ndsi_thresh = ee.Array(NDSI_THRESH_VALUES)
	alpha = ee.Array(ALPHA_VALUES)
	ab_ratio = ee.Array(AB_RATIO_VALUES)
	al_ratio = ee.Array(AL_RATIO_VALUES)
	beta = ee.Array(alpha.divide(ab_ratio))
	lamb = ee.Array(alpha.divide(al_ratio))
	n_runs = len(ALPHA_VALUES)

	stack_stats_t1 = f_stack_stats(1, 30, start_yr_t1, trig_t1, aoi)
	stack_stats_t2 = f_stack_stats(1, 30, trig_t2, end_yr_t2, aoi)

	d_ndvi = stack_stats_t2.select('nd').subtract(stack_stats_t1.select('nd'))
	d_ndvi_sum = d_ndvi
	ndvi_t2_sum = stack_stats_t2.select('nd')
	ndsi_t2_sum = stack_stats_t2.select('ndsi_median')
	d_ndvi_stack = d_ndvi

	for i in range(1, N_MONTHS):
		start_doy = 1 + round(30.4 * i)
		end_doy = start_doy + 30
		stack_stats_t1 = f_stack_stats(start_doy, end_doy, start_yr_t1, trig_t1, aoi)
		stack_stats_t2 = f_stack_stats(start_doy, end_doy, trig_t2, end_yr_t2, aoi)

		d_ndvi = stack_stats_t2.select('nd').subtract(stack_stats_t1.select('nd'))
		d_ndvi_sum = d_ndvi_sum.add(d_ndvi)
		d_ndvi_stack = d_ndvi_stack.addBands(d_ndvi)
		ndvi_t2_sum = ndvi_t2_sum.add(stack_stats_t2.select('nd'))
		ndsi_t2_sum = ndsi_t2_sum.add(stack_stats_t2.select('ndsi_median'))

	d_v = d_ndvi_sum.divide(N_MONTHS)
	v_post = ndvi_t2_sum.divide(N_MONTHS)
	s_post = ndsi_t2_sum.divide(N_MONTHS)

	sum_d = d_ndvi_stack.expression(
		'(b(0)+b(1)+b(2)+b(3)+b(4)+b(5)+b(6)+b(7)+b(8)+b(9)+b(10)+b(11))'
	)
	sum_dsq = d_ndvi_stack.expression(
		'(b(0)**2+b(1)**2+b(2)**2+b(3)**2+b(4)**2+b(5)**2+b(6)**2+b(7)**2+b(8)**2+b(9)**2+b(10)**2+b(11)**2)'
	)
	t_stat = sum_d.expression(
		'sum_d/(((n * sum_dsq - sum_d**2)/(n-1))**0.5)',
		{'sum_d': sum_d, 'n': N_MONTHS, 'sum_dsq': sum_dsq},
	)

	df = ee.Number(N_MONTHS - 1)
	p_t = f_student(t_stat, df)
	p_t = p_t.pow(0).subtract(p_t.divide(2))
	p_t = p_t.multiply(t_stat.lte(0))

	d_v = d_v.multiply(d_v.lte(0))
	s_mask = s_post.lte(ndsi_thresh.get([0]))

	aldi_sum = d_v.expression(
		'(-1*dV)**alpha * (1 - Vpost)**beta * (Pt)**lambda * Smask',
		{
			'dV': d_v,
			'Vpost': v_post,
			'Smask': s_mask,
			'Pt': p_t,
			'alpha': alpha.get([0]),
			'beta': beta.get([0]),
			'lambda': lamb.get([0]),
		},
	)

	for i in range(1, n_runs):
		s_mask = s_post.lte(ndsi_thresh.get([i]))
		my_aldi = d_v.expression(
			'(-1*dV)**alpha * (1 - Vpost)**beta * (Pt)**lambda * Smask',
			{
				'dV': d_v,
				'Vpost': v_post,
				'Smask': s_mask,
				'Pt': p_t,
				'alpha': alpha.get([i]),
				'beta': beta.get([i]),
				'lambda': lamb.get([i]),
			},
		)
		aldi_sum = aldi_sum.add(my_aldi)

	aldi = aldi_sum.divide(n_runs)

	def _mask_clouds(image):
		return f_cloud_mask(image, 50)

	pre_img8 = (
		ee.ImageCollection('LANDSAT/LC09/C02/T1')
		.filterBounds(aoi)
		.filterDate(trig_t1.advance(-2, 'years'), trig_t1)
		.map(f_pan_sharpen_l8)
		.map(_mask_clouds)
		.median()
	)
	post_img8 = (
		ee.ImageCollection('LANDSAT/LC09/C02/T1')
		.filterBounds(aoi)
		.filterDate(trig_t2, trig_t2.advance(2, 'years'))
		.map(f_add_ndvi_l8)
		.map(f_pan_sharpen_l8)
		.map(_mask_clouds)
		.median()
	)
	pre_img7 = (
		ee.ImageCollection('LANDSAT/LC08/C02/T1')
		.filterBounds(aoi)
		.filterDate(trig_t1.advance(-2, 'years'), trig_t1)
		.map(f_pan_sharpen_l7)
		.map(_mask_clouds)
		.median()
	)
	post_img7 = (
		ee.ImageCollection('LANDSAT/LC08/C02/T1')
		.filterBounds(aoi)
		.filterDate(trig_t2, trig_t2.advance(2, 'years'))
		.map(f_pan_sharpen_l7)
		.map(_mask_clouds)
		.median()
	)

	return {
		'aoi': aoi,
		'dV': d_v,
		'Vpost': v_post,
		'Spost': s_post,
		't_stat': t_stat,
		'Pt': p_t,
		'ALDI': aldi,
		'pre_img8': pre_img8,
		'post_img8': post_img8,
		'pre_img7': pre_img7,
		'post_img7': post_img7,
	}


def landslide_area():
	trig_t1 = request.args.get('trigT1') or request.args.get('start')
	trig_t2 = request.args.get('trigT2') or request.args.get('end')
	province = request.args.get('provinceSelect')
	district = request.args.get('districtSelect')
	ll_lon = request.args.get('ll_lon')
	ll_lat = request.args.get('ll_lat')
	ur_lon = request.args.get('ur_lon')
	ur_lat = request.args.get('ur_lat')

	if not trig_t1 or not trig_t2:
		return jsonify({'error': 'Thiếu trigT1 hoặc trigT2'}), 400

	try:
		if province:
			region = get_commune_roi(province, district)
		else:
			if None in (ll_lon, ll_lat, ur_lon, ur_lat):
				return jsonify({'error': 'Thiếu provinceSelect/districtSelect hoặc bộ tọa độ bbox'}), 400
			region = ee.Geometry.Rectangle(float(ll_lon), float(ll_lat), float(ur_lon), float(ur_lat))
	except ValueError as ve:
		return jsonify({'error': str(ve)}), 400
	except Exception as e:
		return jsonify({'error': 'Lỗi khi xây dựng vùng quan tâm: ' + str(e)}), 500

	try:
		result = landslide_aldi(trig_t1, trig_t2, region)
	except ValueError as ve:
		return jsonify({'error': str(ve)}), 400
	except Exception as e:
		return jsonify({'error': 'Lỗi khi xử lý dữ liệu sạt lở: ' + str(e)}), 500

	classified = result['ALDI'].expression(
		"(ALDI <= 0.1) ? 1 : "
		"(ALDI <= 0.3) ? 2 : "
		"(ALDI <= 0.5) ? 3 : "
		"(ALDI <= 0.7) ? 4 : 5",
		{'ALDI': result['ALDI']}
	).rename('class')

	class_area_image = classified.multiply(ee.Image.pixelArea().divide(10000)).rename('class')
	vis_params = {'palette': ['#FF0000'], 'min': 1, 'max': 1}
	map_dict = classified.getMapId(vis_params)
	if 'tile_fetcher' in map_dict:
		tile_url = map_dict['tile_fetcher'].url_format
	elif 'mapid' in map_dict and 'token' in map_dict:
		tile_url = f"https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/{map_dict['mapid']}/tiles/{{z}}/{{x}}/{{y}}?token={map_dict['token']}"
	else:
		tile_url = None

	area = class_area_image.reduceRegion(
		reducer=ee.Reducer.sum(),
		geometry=region,
		scale=10 if district else 100,
		maxPixels=9e13,
		tileScale=4
	).get('class')
	area_ha = area.getInfo() if area is not None else 0

	area_ha_by_commune = None
	try:
		shapefile_path = f"public/commune/hcxa2025_{province}.shp"
		if os.path.exists(shapefile_path):
			gdf_commune = gpd.read_file(shapefile_path)
			if 'tenxa' in gdf_commune.columns:
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
					commune_features.append(
						ee.Feature(
							ee.Geometry(row.geometry.__geo_interface__),
							{'tenxa': row['tenxa']}
						)
					)

				if commune_features:
					commune_fc = ee.FeatureCollection(commune_features)
					commune_area_fc = class_area_image.reduceRegions(
						collection=commune_fc,
						reducer=ee.Reducer.sum(),
						scale=10 if district else 100,
						tileScale=4
					)
					commune_area_info = commune_area_fc.getInfo()
					area_ha_by_commune = []
					for feature in commune_area_info.get('features', []):
						props = feature.get('properties', {})
						area_ha_by_commune.append({
							'tenxa': props.get('tenxa'),
							'area_ha': round(float(props.get('sum') or 0), 4)
						})
					area_ha_by_commune.sort(key=lambda item: item['area_ha'], reverse=True)
	except Exception as ex:
		print('Error preparing commune geometries:', ex)

	return jsonify({
		'ALDI': {
			'tile_url': tile_url,
			'area_ha': area_ha,
			'palette': ['#FF0000'],
			'area_ha_by_commune': area_ha_by_commune,
		}
	})


def main(trig_t1, trig_t2, ll_lon, ll_lat, ur_lon, ur_lat):
	"""Compatibility alias matching the original JavaScript entry point."""
	region = ee.Geometry.Rectangle(float(ll_lon), float(ll_lat), float(ur_lon), float(ur_lat))
	return landslide_aldi(trig_t1, trig_t2, region)


__all__ = [
	'f_gauss',
	'f_student',
	'f_add_ndvi_l8',
	'f_add_ndvi_l457',
	'f_add_ndsi_l8',
	'f_add_ndsi_l457',
	'f_cloud_mask',
	'f_pan_sharpen_l8',
	'f_pan_sharpen_l7',
	'f_stack_stats',
	'get_commune_roi',
	'landslide_area',
	'landslide_aldi',
	'main',
]
