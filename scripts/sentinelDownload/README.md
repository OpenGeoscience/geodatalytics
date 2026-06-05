# Script Description

This Python script downloads and clips Sentinel-2 imagery from the public AWS Earth Search using the STAC API.
It fetches visual (RGB) Cloud-Optimized GeoTIFFs (COGs), extracts a user-defined square window around a given latitude and longitude, and saves the results locally with accompanying JSON ingest file for easy importing into GeoDatalytics.

```bash
uv run --script sentinel2Download.py {arguments}
```

## Use Cases

- **Satellite Imagery Clipping**
  Quickly extract a small area (e.g., 10 km × 10 km) of Sentinel-2 data around a point of interest.

- **Change Detection and Time Series Analysis**
  Download multiple cloud-filtered images over a date range for sequential comparison.

- **Data Preprocessing for ML/AI**
  Clip, clean, and organize imagery before feeding it into machine learning pipelines.

## Inputs

The script accepts command-line options via `click`:

- `--lat` _(float, required)_ - Latitude of the point of interest.
- `--lon` _(float, required)_ - Longitude of the point of interest.
- `--start-date` _(str, default `2025-01-01`)_ - Start date in `YYYY-MM-DD` format.
- `--end-date` _(str, default = today)_ - End date in `YYYY-MM-DD` format.
- `--max-results` _(int, default `5`)_ - Maximum number of images to download.
- `--output-name` _(str, default `sequentialTestRasters`)_ - Base name for output. Rasters are saved under `downloads/<output-name>/`; ingest JSON is written as `<output-name>.json` next to the script.
- `--cloud-cover` _(float, default `30.0`)_ - Maximum allowed cloud cover percentage of files found.
- `--size-km` _(float, default `10.0`)_ - Size of square window (in kilometers) to clip around the point.
- `--single-file` _(flag, default off)_ - Combine all downloaded frames into one multiframe GeoTIFF instead of writing separate files per date. The generated ingest JSON uses `frame_property: "frame"` for multiframe ingest.

### `--single-file` GDAL requirement

The `--single-file` option shells out to `gdal_translate` to append each clipped frame as a subdataset in one multiframe GeoTIFF. GDAL must be installed and `gdal_translate` must be on your `PATH`.

If GDAL is not available, run without `--single-file` (the default writes one GeoTIFF per frame).

---

## Outputs

Files are written relative to this script directory:

```
scripts/sentinelDownload/
  sentinel2Download.py
  <output-name>.json          # ingest manifest (sibling to the script)
  downloads/
    <output-name>/
      *.tif                   # clipped GeoTIFF(s)
```

- **GeoTIFF files** - Clipped Sentinel-2 visual images (RGB). With `--single-file`, one multiframe GeoTIFF is written instead of separate per-date files.
- **`<output-name>.json`** - Ingest manifest describing the project, dataset, layers, and frames.

## Ingesting into GeoDatalytics

Then ingest the sequential data from the project root:

```bash
./manage.py ingest <output-name>.json --replace
```

Use `--replace` if you have previously ingested the same project or dataset and need to refresh it.
