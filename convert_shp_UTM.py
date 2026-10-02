"""Convert ESRI Shapefiles from EPSG:3405 or EPSG:4326 to UTM zone 48N."""

# Example in PowerShell:
# py -3 .\convert_shp_UTM.py "C:\Users\PC\Desktop\thuyhe" -o "C:\Users\PC\Desktop\thuyhe\UTM"

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_SOURCE_CRS = "EPSG:3405"
TARGET_CRS = "EPSG:32648"


def convert_shapefile(
	input_path: Path, output_path: Path, source_crs: str | None = None
) -> None:
	"""Reproject one shapefile and write it to ``output_path``."""
	try:
		import geopandas as gpd
	except ImportError as error:
		raise RuntimeError(
			"GeoPandas is required. Install project dependencies with "
			"'py -3 -m pip install geopandas'."
		) from error

	data = gpd.read_file(input_path)

	if data.crs is None:
		data = data.set_crs(source_crs or DEFAULT_SOURCE_CRS)
	elif source_crs and data.crs != source_crs:
		print(
			f"Warning: {input_path} declares CRS {data.crs}; "
			f"overriding it with {source_crs}."
		)
		data = data.set_crs(source_crs, allow_override=True)

	output_path.parent.mkdir(parents=True, exist_ok=True)
	data.to_crs(TARGET_CRS).to_file(output_path, driver="ESRI Shapefile")
	print(f"Converted: {input_path} -> {output_path}")


def find_shapefiles(input_path: Path) -> list[Path]:
	"""Return the input file or all shapefiles in the input directory."""
	if input_path.is_file():
		if input_path.suffix.lower() != ".shp":
			raise ValueError(f"Input file is not a shapefile: {input_path}")
		return [input_path]

	if input_path.is_dir():
		return sorted(input_path.glob("*.shp"))

	raise FileNotFoundError(f"Input path does not exist: {input_path}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Convert *.shp files from EPSG:3405 or EPSG:4326 to EPSG:32648."
	)
	parser.add_argument(
		"input",
		type=Path,
		help="Input .shp file or directory containing .shp files.",
	)
	parser.add_argument(
		"-o",
		"--output",
		type=Path,
		help="Output .shp file or directory. Defaults to <input>_utm48.",
	)
	parser.add_argument(
		"--source-crs",
		default=None,
		help=(
			"Override the source CRS, for example EPSG:3405 or EPSG:4326. "
			f"For files without .prj, defaults to {DEFAULT_SOURCE_CRS}."
		),
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	shapefiles = find_shapefiles(args.input)

	if not shapefiles:
		raise FileNotFoundError(f"No .shp files found in: {args.input}")

	if args.input.is_file():
		output_path = args.output or args.input.with_name(
			f"{args.input.stem}_utm48{args.input.suffix}"
		)
		convert_shapefile(args.input, output_path, args.source_crs)
		return

	output_dir = args.output or args.input.parent / f"{args.input.name}_utm48"
	output_dir.mkdir(parents=True, exist_ok=True)
	for shapefile in shapefiles:
		convert_shapefile(shapefile, output_dir / shapefile.name, args.source_crs)


if __name__ == "__main__":
	main()
