# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "click",
#     "pystac-client",
#     "requests",
#     "shapely",
#     "rasterio",
#     "pyproj",
# ]
# ///
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import click
import numpy as np
from pyproj import Transformer
from pystac_client import Client
import rasterio
from rasterio.errors import RasterioError, RasterioIOError
from rasterio.windows import from_bounds
from shapely.geometry import Point, mapping

# STAC API from AWS Earth Search
STAC_API_URL = "https://earth-search.aws.element84.com/v1"
SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"


def default_end_date():
    return datetime.now(tz=UTC).date().isoformat()


def read_cog_window(cog_url, lon, lat, size_km=10):
    """
    Read a size_km x size_km window from the remote COG at lon, lat.

    Returns numpy array data and updated affine transform.
    """
    with rasterio.Env(), rasterio.open(cog_url) as src:
        # Convert lat/lon to image CRS coordinates
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = transformer.transform(lon, lat)

        half_size_m = (size_km * 1000) / 2
        bounds = (x - half_size_m, y - half_size_m, x + half_size_m, y + half_size_m)
        window = from_bounds(*bounds, transform=src.transform)

        data = src.read(1, window=window)
        transform = src.window_transform(window)

        # Copy metadata for output
        meta = src.meta.copy()
        meta.update(
            {
                "height": data.shape[0],
                "width": data.shape[1],
                "transform": transform,
            }
        )

        return data, meta


def read_cog_window_rgb(cog_url, lon, lat, size_km=10):
    """
    Read a size_km x size_km window from the remote COG at lon, lat.

    Returns 3-band numpy array data (RGB) and updated affine transform.
    """
    with rasterio.Env(), rasterio.open(cog_url) as src:
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = transformer.transform(lon, lat)

        half_size_m = (size_km * 1000) / 2
        bounds = (x - half_size_m, y - half_size_m, x + half_size_m, y + half_size_m)
        click.echo(f"  - Window bounds: {bounds}")
        window = from_bounds(*bounds, transform=src.transform)

        # Read bands 1,2,3 (RGB)
        bands = []
        for b in [1, 2, 3]:
            band_data = src.read(b, window=window)
            bands.append(band_data)

        data = np.stack(bands)  # shape: (3, height, width)

        transform = src.window_transform(window)
        meta = src.meta.copy()
        meta.update(
            {
                "count": 3,
                "height": data.shape[1],
                "width": data.shape[2],
                "transform": transform,
                "dtype": data.dtype,
            }
        )

        return data, meta


def combine_frames_to_multiframe(frame_paths, output_path):
    """
    Combine single-frame GeoTIFFs into one multiframe GeoTIFF.

    Each appended page becomes a scrubbable frame when imported with
    frame_property: "frame".
    """
    if not frame_paths:
        return

    gdal_translate = shutil.which("gdal_translate")
    if gdal_translate is None:
        msg = (
            "gdal_translate is required for --single-file but was not found on PATH. "
            "Install GDAL or run without --single-file."
        )
        raise RuntimeError(msg)

    output_path = Path(output_path)
    creation_options = ["-co", "COMPRESS=LZW"]
    subprocess.run(
        [gdal_translate, *creation_options, str(frame_paths[0]), str(output_path)],
        check=True,
    )
    for frame_path in frame_paths[1:]:
        subprocess.run(
            [
                gdal_translate,
                *creation_options,
                "-co",
                "APPEND_SUBDATASET=YES",
                str(frame_path),
                str(output_path),
            ],
            check=True,
        )


@click.command()
@click.option(
    "--lat", default=43.135763, type=float, required=True, help="Latitude of the location."
)
@click.option(
    "--lon", default=-74.1767949, type=float, required=True, help="Longitude of the location."
)
@click.option(
    "--start-date",
    type=str,
    default="2025-01-01",
    show_default=True,
    help="Start date (YYYY-MM-DD).",
)
@click.option(
    "--end-date",
    type=str,
    default=default_end_date,
    show_default=True,
    help="End date (YYYY-MM-DD).",
)
@click.option(
    "--max-results",
    type=int,
    default=5,
    show_default=True,
    help="Maximum number of images to download.",
)
@click.option(
    "--output-name",
    type=str,
    default="sequentialTestRasters",
    show_default=True,
    help=(
        "Base name for output: writes rasters to downloads/<output-name>/ and "
        "a sibling ingest JSON named <output-name>.json next to this script."
    ),
)
@click.option(
    "--cloud-cover", type=float, default=30.0, show_default=True, help="Max cloud cover percentage."
)
@click.option(
    "--size-km",
    type=float,
    default=10.0,
    show_default=True,
    help="Size of square window to clip around the point in kilometers.",
)
@click.option(
    "--single-file",
    is_flag=True,
    default=False,
    help=(
        "Write all frames into one multiframe GeoTIFF instead of separate files. "
        "The generated output JSON will use frame_property: \"frame\"."
    ),
)
def download_stac_sentinel(  # noqa: PLR0913, PLR0915
    lat, lon, start_date, end_date, max_results, output_name, cloud_cover, size_km, single_file
):
    """Download clipped Sentinel-2 L1C visual images from AWS via STAC API."""
    output_dir = DOWNLOADS_DIR / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    catalog = Client.open(STAC_API_URL)

    # Point geometry as GeoJSON
    point = Point(lon, lat)
    geom = mapping(point)

    search = catalog.search(
        collections=["sentinel-2-c1-l2a"],
        intersects=geom,
        datetime=f"{start_date}/{end_date}",
        query={"eo:cloud_cover": {"lt": cloud_cover}},
        limit=max_results,
    )

    items = list(search.items())

    if not items:
        click.echo("⚠️  No Sentinel-2 images found.")
        click.echo("🔍 Search parameters used:")
        click.echo(f"    - Location: lat={lat}, lon={lon}")
        click.echo(f"    - Date range: {start_date} to {end_date}")
        click.echo(f"    - Cloud cover < {cloud_cover}%")
        click.echo("    - Collection: sentinel-2-c1-l2a")
        click.echo(f"    - Max results: {max_results}")
        click.echo("💡 Suggestions:")
        click.echo("    - Try a wider date range.")
        click.echo("    - Increase the allowed cloud cover (e.g., --cloud-cover 60).")
        click.echo("    - Confirm Sentinel-2 covers your area and date range.")
        return

    click.echo(
        f"✅ Found {len(items)} items. Downloading up to {max_results} clipped visual images..."
    )

    downloaded_files = []
    downloaded_frame_paths = []
    multiframe_filename = None

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        for i, item in enumerate(items):
            if i >= max_results:
                break
            date_str = item.datetime.strftime("%Y-%m-%d")
            item_id = item.id
            click.echo(f"[{i + 1}/{len(items)}] {item_id} from {date_str}")

            visual_asset = item.assets.get("visual")
            if visual_asset:
                url = visual_asset.href
                filename = f"{item_id}_visual_clip_{int(size_km)}km.tif"
                filepath = output_dir / filename
                write_path = temp_path / filename if single_file else filepath

                click.echo(f"  - Reading {size_km}km x {size_km}km window around point")
                try:
                    data, meta = read_cog_window_rgb(url, lon, lat, size_km=size_km)
                    with rasterio.open(write_path, "w", **meta) as dst:
                        dst.write(data)
                except (RasterioError, RasterioIOError) as e:
                    click.echo(f"  - ⚠️ Failed to read or save clipped image: {e}")
                else:
                    if single_file:
                        click.echo(f"  - Buffered frame {len(downloaded_frame_paths)}")
                        downloaded_frame_paths.append(write_path)
                    else:
                        click.echo(f"  - Saved clipped image to {filename}")
                    downloaded_files.append(filename)
            else:
                click.echo(f"  - ⚠️ Visual asset not available in item {item_id}")

        if single_file and downloaded_frame_paths:
            multiframe_filename = f"sentinel_visual_clip_{int(size_km)}km_multiframe.tif"
            multiframe_path = output_dir / multiframe_filename
            click.echo(
                f"Combining {len(downloaded_frame_paths)} frames into {multiframe_filename}..."
            )
            combine_frames_to_multiframe(downloaded_frame_paths, multiframe_path)
            click.echo(f"  - Saved multiframe image to {multiframe_filename}")

    click.echo("✅ Download complete.")
    dataset_json = {
        "type": "Dataset",
        "name": "Sequential Test Rasters",
        "description": "Clipped Sentinel-2 images downloaded and clipped around point",
        "category": "imagery",
        "tags": ["sentinel-2", "imagery", "sequential"],
        "files": [],
        "layers": [],
    }

    project_json = {
        "type": "Project",
        "name": "Sentinel-2 Clipped Images",
        "datasets": ["Sequential Test Rasters"],
        "default_map_center": [lon, lat],
        "default_map_zoom": 11,
    }

    if single_file and multiframe_filename:
        dataset_json["files"].append(
            {"path": f"{output_name}/{multiframe_filename}", "name": multiframe_filename}
        )
        dataset_json["layers"].append(
            {
                "name": "Sequential Test Layers",
                "frame_property": "frame",
                "data": multiframe_filename,
            }
        )
    else:
        layer_frames = []
        for idx, f in enumerate(downloaded_files):
            dataset_json["files"].append({"path": f"{output_name}/{f}", "name": f"Frame {idx}"})
            layer_frames.append(
                {
                    "name": f"Sequential Layer {idx}",
                    "index": idx,
                    "data": f,
                }
            )

        dataset_json["layers"].append({"name": "Sequential Test Layers", "frames": layer_frames})

    json_path = SCRIPT_DIR / f"{output_name}.json"
    with json_path.open("w") as jf:
        json.dump([project_json, dataset_json], jf, indent=4)
    click.echo(f"  - Wrote ingest JSON to {json_path}")
    click.echo(f"  - Rasters saved under {output_dir}")


if __name__ == "__main__":
    download_stac_sentinel()
