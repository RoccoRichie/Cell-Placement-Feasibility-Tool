"""Fetch geospatial exclusion data for all of Ireland."""
import os
import sys
import time
import logging
import requests
import geopandas as gpd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")

# --- Logging setup ---
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger("fetch_data")
logger.setLevel(logging.INFO)

_file_handler = logging.FileHandler(os.path.join(LOG_DIR, "fetch_data.log"))
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_console_handler)


# --- Progress bar ---
def _progress_bar(current: int, total: int, label: str, width: int = 40):
    pct = current / total if total else 1
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    sys.stdout.write(f"\r  {label} [{bar}] {pct:.0%}")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")


def _download_with_progress(url: str, dest: str, label: str):
    """Download a file with a progress bar."""
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                _progress_bar(downloaded, total, label)
    if not total:
        print(f"  {label} — downloaded")


# --- Fetch functions ---

def fetch_coastline(data_dir: str = DATA_DIR):
    logger.info("━━━ Step 1/5: Ireland land boundary (Natural Earth) ━━━")
    url = (
        "https://naciscdn.org/naturalearth/10m/cultural/"
        "ne_10m_admin_0_countries.zip"
    )
    out = os.path.join(data_dir, "ne_10m_admin_0_countries.zip")
    geojson_out = os.path.join(data_dir, "ireland_boundary.geojson")

    if os.path.exists(geojson_out):
        logger.info("  Already exists — skipping")
        return

    if not os.path.exists(out):
        logger.info("  Downloading country boundaries...")
        _download_with_progress(url, out, "Downloading")

    logger.info("  Extracting Ireland boundary...")
    gdf = gpd.read_file(f"zip://{out}")
    ireland = gdf[gdf["NAME"] == "Ireland"]
    ireland.to_file(geojson_out, driver="GeoJSON")
    logger.info(f"  ✅ Saved Ireland boundary ({len(ireland)} features)")


def fetch_osm_ireland(data_dir: str = DATA_DIR):
    """
    Download the full Ireland OSM extract from Geofabrik,
    then extract water bodies and protected areas from it.
    """
    shp_url = "https://download.geofabrik.de/europe/ireland-and-northern-ireland-latest-free.shp.zip"
    shp_zip = os.path.join(data_dir, "ireland-osm.shp.zip")

    water_out = os.path.join(data_dir, "water_bodies.geojson")
    protected_out = os.path.join(data_dir, "protected_areas.geojson")

    if os.path.exists(water_out) and os.path.exists(protected_out):
        logger.info("━━━ Step 2/5: Water bodies (Geofabrik OSM) ━━━")
        logger.info("  Already exists — skipping")
        logger.info("━━━ Step 3/5: Protected areas (Geofabrik OSM) ━━━")
        logger.info("  Already exists — skipping")
        return

    # Download the shapefile bundle
    if not os.path.exists(shp_zip):
        logger.info("━━━ Step 2–3: Downloading Ireland OSM extract (Geofabrik) ━━━")
        logger.info("  This is a one-time download (~80MB)...")
        _download_with_progress(shp_url, shp_zip, "Ireland OSM")
    else:
        logger.info("━━━ Step 2–3: Processing Ireland OSM extract ━━━")
        logger.info("  Archive already downloaded")

    # Extract water bodies
    if not os.path.exists(water_out):
        logger.info("")
        logger.info("━━━ Step 2/5: Water bodies ━━━")
        logger.info("  Extracting water polygons from OSM data...")
        try:
            water = gpd.read_file(
                f"zip://{shp_zip}",
                layer="gis_osm_water_a_free_1",
            )
            water = water[water.geometry.notnull() & ~water.geometry.is_empty]
            water.to_file(water_out, driver="GeoJSON")
            logger.info(f"  ✅ Saved {len(water)} water body features")
        except Exception as e:
            logger.error(f"  ❌ Failed to extract water bodies: {e}")
            _try_alternative_water_layer(shp_zip, water_out)

    # Extract protected areas / nature reserves
    if not os.path.exists(protected_out):
        logger.info("")
        logger.info("━━━ Step 3/5: Protected areas ━━━")
        logger.info("  Extracting protected area polygons from OSM data...")
        try:
            protected_frames = []
            for layer_name in ["gis_osm_landuse_a_free_1", "gis_osm_natural_a_free_1"]:
                try:
                    gdf = gpd.read_file(f"zip://{shp_zip}", layer=layer_name)
                    if "fclass" in gdf.columns:
                        matches = gdf[gdf["fclass"].isin([
                            "nature_reserve", "national_park", "protected_area",
                            "park", "forest",
                        ])]
                        if len(matches) > 0:
                            protected_frames.append(matches)
                            logger.info(f"    Found {len(matches)} features in {layer_name}")
                except Exception:
                    pass

            if protected_frames:
                import pandas as pd
                protected = gpd.GeoDataFrame(pd.concat(protected_frames, ignore_index=True))
                protected = protected[protected.geometry.notnull() & ~protected.geometry.is_empty]
                protected.to_file(protected_out, driver="GeoJSON")
                logger.info(f"  ✅ Saved {len(protected)} protected area features")
            else:
                logger.warning("  ⚠️  No protected area features found in OSM data")
        except Exception as e:
            logger.error(f"  ❌ Failed to extract protected areas: {e}")


def _try_alternative_water_layer(shp_zip: str, water_out: str):
    """Try alternative layer names for water in the Geofabrik extract."""
    import fiona
    try:
        layers = fiona.listlayers(f"zip://{shp_zip}")
        logger.info(f"  Available layers: {layers}")
        water_layers = [l for l in layers if "water" in l.lower()]
        if water_layers:
            logger.info(f"  Trying layer: {water_layers[0]}")
            water = gpd.read_file(f"zip://{shp_zip}", layer=water_layers[0])
            water = water[water.geometry.notnull() & ~water.geometry.is_empty]
            water.to_file(water_out, driver="GeoJSON")
            logger.info(f"  ✅ Saved {len(water)} water body features")
    except Exception as e:
        logger.error(f"  ❌ Could not find water layer: {e}")


def fetch_dem(data_dir: str = DATA_DIR):
    """
    Download Copernicus DEM GLO-30 tiles for Ireland from AWS Open Data
    and merge them into a single GeoTIFF.
    """
    logger.info("━━━ Step 4/5: DEM elevation data (Copernicus GLO-30) ━━━")
    dem_path = os.path.join(data_dir, "copernicus_dem.tif")
    if os.path.exists(dem_path):
        logger.info("  Already exists — skipping")
        return True

    # Ireland spans roughly N51-N55, W006-W011
    tiles = []
    for lat in range(51, 56):
        for lon in range(-11, -5):
            lon_str = f"W{abs(lon):03d}" if lon < 0 else f"E{abs(lon):03d}"
            lat_str = f"N{lat:02d}"
            tile_name = f"Copernicus_DSM_COG_10_{lat_str}_00_{lon_str}_00_DEM"
            url = f"https://copernicus-dem-30m.s3.amazonaws.com/{tile_name}/{tile_name}.tif"
            tiles.append((tile_name, url))

    tile_dir = os.path.join(data_dir, "dem_tiles")
    os.makedirs(tile_dir, exist_ok=True)

    downloaded = []
    for i, (name, url) in enumerate(tiles):
        tile_path = os.path.join(tile_dir, f"{name}.tif")
        if os.path.exists(tile_path):
            downloaded.append(tile_path)
            continue
        try:
            _download_with_progress(url, tile_path, f"DEM tile {i+1}/{len(tiles)} ({name[:30]}...)")
            downloaded.append(tile_path)
        except Exception:
            # Some tiles may not exist (ocean areas) — skip
            logger.info(f"  Tile {name} not available (likely ocean) — skipping")

    if not downloaded:
        logger.error("  ❌ No DEM tiles downloaded")
        return False

    # Merge tiles into single file
    logger.info(f"  Merging {len(downloaded)} tiles...")
    import rasterio
    from rasterio.merge import merge
    datasets = [rasterio.open(p) for p in downloaded]
    mosaic, transform = merge(datasets)
    meta = datasets[0].meta.copy()
    meta.update({
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": transform,
    })
    for ds in datasets:
        ds.close()

    with rasterio.open(dem_path, "w", **meta) as dest:
        dest.write(mosaic)

    logger.info(f"  ✅ Saved merged DEM ({len(downloaded)} tiles)")
    return True


def fetch_corine_land_cover(data_dir: str = DATA_DIR):
    logger.info("━━━ Step 5/5: CORINE land cover (manual download) ━━━")
    clc_path = os.path.join(data_dir, "corine_clc.gpkg")
    if os.path.exists(clc_path):
        logger.info("  ✅ CORINE data found")
        return True
    else:
        logger.info("  ⚠️  CORINE not found — land cover checks will be skipped")
        logger.info("  Download from:")
        logger.info("    https://land.copernicus.eu/pan-european/corine-land-cover")
        logger.info(f"    Place in: {data_dir}/corine_clc.gpkg")
        return False


def fetch_all(data_dir: str = DATA_DIR):
    os.makedirs(data_dir, exist_ok=True)
    start = time.time()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     Cell Placement Tool — Geospatial Data Download      ║")
    print("║                  All of Ireland                         ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    fetch_coastline(data_dir)
    print()
    fetch_osm_ireland(data_dir)
    print()
    fetch_dem(data_dir)
    print()
    fetch_corine_land_cover(data_dir)

    elapsed = time.time() - start
    print()
    print(f"{'━' * 58}")
    logger.info(f"✅ Data fetch complete in {elapsed:.1f}s")
    logger.info(f"   Data directory: {os.path.abspath(data_dir)}")
    print(f"{'━' * 58}")
    print()


if __name__ == "__main__":
    fetch_all()
