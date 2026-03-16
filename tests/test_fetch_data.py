"""Tests for fetch_data.py."""
import os
import json
import zipfile
import pytest
import geopandas as gpd
from shapely.geometry import Polygon, box
from unittest.mock import patch, MagicMock

from src.fetch_data import (
    fetch_coastline,
    fetch_osm_ireland,
    fetch_dem,
    fetch_corine_land_cover,
    _download_with_progress,
    _progress_bar,
)


# --- Helpers to create fake source data ---

def _create_fake_natural_earth_zip(path: str):
    """Create a minimal zip that gpd.read_file can parse, containing a country."""
    gdf = gpd.GeoDataFrame(
        {"NAME": ["Ireland", "France"]},
        geometry=[
            box(-10.7, 51.4, -5.9, 55.5),
            box(-5.0, 42.0, 8.0, 51.0),
        ],
        crs="EPSG:4326",
    )
    # Write to a temp shapefile inside a zip
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, "ne_10m_admin_0_countries.shp")
        gdf.to_file(shp_path)
        with zipfile.ZipFile(path, "w") as zf:
            for f in os.listdir(tmpdir):
                zf.write(os.path.join(tmpdir, f), f)


def _create_fake_osm_zip(path: str):
    """Create a minimal zip with water and landuse layers."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # Water layer
        water = gpd.GeoDataFrame(
            {"name": ["Lake1"], "fclass": ["water"]},
            geometry=[Polygon([(-8, 52.5), (-7.9, 52.5), (-7.9, 52.6), (-8, 52.6)])],
            crs="EPSG:4326",
        )
        water_path = os.path.join(tmpdir, "gis_osm_water_a_free_1.shp")
        water.to_file(water_path)

        # Landuse layer with a nature reserve
        landuse = gpd.GeoDataFrame(
            {"name": ["Reserve1"], "fclass": ["nature_reserve"]},
            geometry=[Polygon([(-9.5, 52), (-9.4, 52), (-9.4, 52.1), (-9.5, 52.1)])],
            crs="EPSG:4326",
        )
        landuse_path = os.path.join(tmpdir, "gis_osm_landuse_a_free_1.shp")
        landuse.to_file(landuse_path)

        # Natural layer with a park
        natural = gpd.GeoDataFrame(
            {"name": ["Park1"], "fclass": ["national_park"]},
            geometry=[Polygon([(-8.5, 53), (-8.4, 53), (-8.4, 53.1), (-8.5, 53.1)])],
            crs="EPSG:4326",
        )
        natural_path = os.path.join(tmpdir, "gis_osm_natural_a_free_1.shp")
        natural.to_file(natural_path)

        with zipfile.ZipFile(path, "w") as zf:
            for f in os.listdir(tmpdir):
                zf.write(os.path.join(tmpdir, f), f)


# --- Tests ---

class TestFetchCoastline:
    """Tests for fetch_coastline."""

    def test_skips_if_already_exists(self, tmp_path):
        geojson = tmp_path / "ireland_boundary.geojson"
        geojson.write_text("{}")
        fetch_coastline(str(tmp_path))
        # File should be unchanged (not overwritten)
        assert geojson.read_text() == "{}"

    def test_extracts_ireland_from_zip(self, tmp_path):
        zip_path = str(tmp_path / "ne_10m_admin_0_countries.zip")
        _create_fake_natural_earth_zip(zip_path)
        fetch_coastline(str(tmp_path))

        geojson_path = tmp_path / "ireland_boundary.geojson"
        assert geojson_path.exists()
        gdf = gpd.read_file(geojson_path)
        assert len(gdf) == 1
        assert gdf.iloc[0]["NAME"] == "Ireland"

    def test_does_not_include_other_countries(self, tmp_path):
        zip_path = str(tmp_path / "ne_10m_admin_0_countries.zip")
        _create_fake_natural_earth_zip(zip_path)
        fetch_coastline(str(tmp_path))

        gdf = gpd.read_file(tmp_path / "ireland_boundary.geojson")
        assert "France" not in gdf["NAME"].values

    @patch("src.fetch_data._download_with_progress")
    def test_downloads_if_zip_missing(self, mock_dl, tmp_path):
        # Should attempt download when zip doesn't exist
        # Will fail after download since the mock doesn't create a real file,
        # but we verify the download was attempted
        try:
            fetch_coastline(str(tmp_path))
        except Exception:
            pass
        mock_dl.assert_called_once()


class TestFetchOsmIreland:
    """Tests for fetch_osm_ireland."""

    def test_skips_if_both_outputs_exist(self, tmp_path):
        (tmp_path / "water_bodies.geojson").write_text("{}")
        (tmp_path / "protected_areas.geojson").write_text("{}")
        fetch_osm_ireland(str(tmp_path))
        # Files unchanged
        assert (tmp_path / "water_bodies.geojson").read_text() == "{}"

    def test_extracts_water_bodies(self, tmp_path):
        zip_path = str(tmp_path / "ireland-osm.shp.zip")
        _create_fake_osm_zip(zip_path)
        fetch_osm_ireland(str(tmp_path))

        water_path = tmp_path / "water_bodies.geojson"
        assert water_path.exists()
        gdf = gpd.read_file(water_path)
        assert len(gdf) >= 1

    def test_extracts_protected_areas(self, tmp_path):
        zip_path = str(tmp_path / "ireland-osm.shp.zip")
        _create_fake_osm_zip(zip_path)
        fetch_osm_ireland(str(tmp_path))

        protected_path = tmp_path / "protected_areas.geojson"
        assert protected_path.exists()
        gdf = gpd.read_file(protected_path)
        assert len(gdf) >= 1

    def test_protected_areas_filters_by_fclass(self, tmp_path):
        zip_path = str(tmp_path / "ireland-osm.shp.zip")
        _create_fake_osm_zip(zip_path)
        fetch_osm_ireland(str(tmp_path))

        gdf = gpd.read_file(tmp_path / "protected_areas.geojson")
        assert all(
            fc in ["nature_reserve", "national_park", "protected_area", "park", "forest"]
            for fc in gdf["fclass"]
        )

    @patch("src.fetch_data._download_with_progress")
    def test_downloads_if_zip_missing(self, mock_dl, tmp_path):
        try:
            fetch_osm_ireland(str(tmp_path))
        except Exception:
            pass
        mock_dl.assert_called_once()


class TestFetchDem:
    """Tests for fetch_dem."""

    def test_returns_true_when_dem_exists(self, tmp_path):
        (tmp_path / "copernicus_dem.tif").write_text("fake")
        assert fetch_dem(str(tmp_path)) is True

    @patch("src.fetch_data._download_with_progress", side_effect=Exception("no network"))
    def test_returns_false_when_no_tiles_available(self, mock_dl, tmp_path):
        assert fetch_dem(str(tmp_path)) is False


class TestFetchCorineLandCover:
    """Tests for fetch_corine_land_cover."""

    def test_returns_true_when_corine_exists(self, tmp_path):
        (tmp_path / "corine_clc.gpkg").write_text("fake")
        assert fetch_corine_land_cover(str(tmp_path)) is True

    def test_returns_false_when_corine_missing(self, tmp_path):
        assert fetch_corine_land_cover(str(tmp_path)) is False


class TestDownloadWithProgress:
    """Tests for _download_with_progress."""

    @patch("src.fetch_data.requests.get")
    def test_writes_response_to_file(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": "5"}
        mock_resp.iter_content.return_value = [b"hello"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        dest = str(tmp_path / "test.bin")
        _download_with_progress("http://example.com/file", dest, "Test")

        assert os.path.exists(dest)
        with open(dest, "rb") as f:
            assert f.read() == b"hello"

    @patch("src.fetch_data.requests.get")
    def test_raises_on_http_error(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")
        mock_get.return_value = mock_resp

        with pytest.raises(Exception, match="404"):
            _download_with_progress("http://example.com/bad", str(tmp_path / "x"), "Test")


class TestProgressBar:
    """Tests for _progress_bar."""

    def test_full_progress(self, capsys):
        _progress_bar(100, 100, "Test")
        captured = capsys.readouterr()
        assert "100%" in captured.out

    def test_zero_total(self, capsys):
        _progress_bar(0, 0, "Test")
        captured = capsys.readouterr()
        assert "100%" in captured.out

    def test_partial_progress(self, capsys):
        _progress_bar(50, 100, "Test")
        captured = capsys.readouterr()
        assert "50%" in captured.out
