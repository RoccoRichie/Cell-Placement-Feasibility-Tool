"""Shared test fixtures for feasibility checker tests."""
import os
import pytest
import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon, box


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temp data directory with synthetic geospatial test data."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Ireland boundary — simplified rectangle covering the country
    ireland_poly = box(-10.7, 51.4, -5.9, 55.5)
    ireland = gpd.GeoDataFrame(
        {"NAME": ["Ireland"]},
        geometry=[ireland_poly],
        crs="EPSG:4326",
    )
    ireland.to_file(data_dir / "ireland_boundary.geojson", driver="GeoJSON")

    # Water body — a fake lake in the middle of Ireland
    lake_poly = Polygon([
        (-8.0, 52.5), (-7.9, 52.5), (-7.9, 52.6), (-8.0, 52.6), (-8.0, 52.5)
    ])
    water = gpd.GeoDataFrame(
        {"name": ["Test Lake"]},
        geometry=[lake_poly],
        crs="EPSG:4326",
    )
    water.to_file(data_dir / "water_bodies.geojson", driver="GeoJSON")

    # Protected area — a fake nature reserve
    reserve_poly = Polygon([
        (-9.5, 52.0), (-9.4, 52.0), (-9.4, 52.1), (-9.5, 52.1), (-9.5, 52.0)
    ])
    protected = gpd.GeoDataFrame(
        {"name": ["Test Reserve"], "fclass": ["nature_reserve"]},
        geometry=[reserve_poly],
        crs="EPSG:4326",
    )
    protected.to_file(data_dir / "protected_areas.geojson", driver="GeoJSON")

    # CORINE — a bog polygon
    bog_poly = Polygon([
        (-7.5, 53.0), (-7.4, 53.0), (-7.4, 53.1), (-7.5, 53.1), (-7.5, 53.0)
    ])
    corine = gpd.GeoDataFrame(
        {"code_18": [412]},  # 412 = Peat bogs
        geometry=[bog_poly],
        crs="EPSG:4326",
    )
    corine.to_file(data_dir / "corine_clc.gpkg", driver="GPKG")

    return str(data_dir)
