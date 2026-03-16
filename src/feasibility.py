"""Feasibility checker for telecom cell placement in Ireland."""
import logging
import os
import numpy as np
import geopandas as gpd
import rasterio
from shapely.geometry import Point

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
logger = logging.getLogger("feasibility")

# CORINE codes that are infeasible for cell placement
INFEASIBLE_CORINE_CODES = {
    411,  # Inland marshes
    412,  # Peat bogs
    421,  # Salt marshes
    422,  # Salines
    423,  # Intertidal flats
    511,  # Water courses
    512,  # Water bodies
    521,  # Coastal lagoons
    522,  # Estuaries
    523,  # Sea and ocean
}

MAX_SLOPE_DEGREES = 20.0  # Reject sites steeper than this

# Layers: (attribute name, filename, required)
_LAYERS = [
    ("_ireland", "ireland_boundary.geojson", True),
    ("_water", "water_bodies.geojson", True),
    ("_protected", "protected_areas.geojson", True),
    ("_corine", "corine_clc.gpkg", False),
]


class FeasibilityChecker:
    def __init__(self, data_dir: str = DATA_DIR, eager: bool = False):
        self.data_dir = data_dir
        self._ireland = None
        self._water = None
        self._protected = None
        self._corine = None
        self._dem_dataset = None
        if eager:
            self._load_all()
            self._get_dem()

    def _load_layer(self, filename: str) -> gpd.GeoDataFrame | None:
        path = os.path.join(self.data_dir, filename)
        if os.path.exists(path):
            return gpd.read_file(path)
        return None

    def _load_all(self):
        for attr, filename, _ in _LAYERS:
            if getattr(self, attr) is None:
                try:
                    setattr(self, attr, self._load_layer(filename))
                except Exception as e:
                    logger.error(f"Failed to load {filename}: {e}")
                    setattr(self, attr, None)

    def _get_dem(self):
        if self._dem_dataset is None:
            dem_path = os.path.join(self.data_dir, "copernicus_dem.tif")
            if os.path.exists(dem_path):
                try:
                    self._dem_dataset = rasterio.open(dem_path)
                except Exception as e:
                    logger.error(f"Failed to load DEM: {e}")
        return self._dem_dataset

    def reload(self):
        """Force reload all layers. Used for self-healing."""
        logger.info("Reloading all geospatial layers...")
        self._ireland = None
        self._water = None
        self._protected = None
        self._corine = None
        if self._dem_dataset:
            try:
                self._dem_dataset.close()
            except Exception:
                pass
        self._dem_dataset = None
        self._load_all()
        self._get_dem()
        logger.info("Reload complete")

    def health(self) -> dict:
        """Return health status of each data layer."""
        layers = {}
        for attr, filename, required in _LAYERS:
            data = getattr(self, attr)
            path = os.path.join(self.data_dir, filename)
            if data is not None and len(data) > 0:
                layers[filename] = {"status": "loaded", "features": len(data)}
            elif os.path.exists(path):
                layers[filename] = {"status": "file_exists_but_not_loaded"}
            else:
                layers[filename] = {"status": "missing", "required": required}

        dem_path = os.path.join(self.data_dir, "copernicus_dem.tif")
        if self._dem_dataset and not self._dem_dataset.closed:
            layers["copernicus_dem.tif"] = {"status": "loaded"}
        elif os.path.exists(dem_path):
            layers["copernicus_dem.tif"] = {"status": "file_exists_but_not_loaded"}
        else:
            layers["copernicus_dem.tif"] = {"status": "missing", "required": False}

        required_ok = all(
            getattr(self, attr) is not None
            for attr, _, required in _LAYERS if required
        )

        return {
            "healthy": required_ok,
            "layers": layers,
        }

    def is_on_land(self, lat: float, lon: float) -> bool:
        self._load_all()
        if self._ireland is None:
            return True
        point = Point(lon, lat)
        return bool(self._ireland.geometry.contains(point).any())

    def is_in_water(self, lat: float, lon: float) -> bool:
        self._load_all()
        if self._water is None:
            return False
        point = Point(lon, lat)
        return bool(self._water.geometry.contains(point).any())

    def is_in_protected_area(self, lat: float, lon: float) -> bool:
        self._load_all()
        if self._protected is None:
            return False
        point = Point(lon, lat)
        return bool(self._protected.geometry.contains(point).any())

    def get_corine_code(self, lat: float, lon: float) -> int | None:
        self._load_all()
        if self._corine is None:
            return None
        point = Point(lon, lat)
        matches = self._corine[self._corine.geometry.contains(point)]
        if len(matches) > 0:
            return int(matches.iloc[0].get("code_18", matches.iloc[0].get("Code_18", 0)))
        return None

    def get_slope(self, lat: float, lon: float) -> float | None:
        dem = self._get_dem()
        if dem is None:
            return None
        try:
            row, col = dem.index(lon, lat)
            window = rasterio.windows.Window(col - 1, row - 1, 3, 3)
            elev = dem.read(1, window=window)
            if elev.shape != (3, 3):
                return None
            # Convert pixel resolution from degrees to meters
            res_deg = dem.res[0]
            res_m = res_deg * 111320 * np.cos(np.radians(lat))
            dzdx = ((elev[0, 2] + 2 * elev[1, 2] + elev[2, 2]) -
                     (elev[0, 0] + 2 * elev[1, 0] + elev[2, 0])) / (8 * res_m)
            dzdy = ((elev[2, 0] + 2 * elev[2, 1] + elev[2, 2]) -
                     (elev[0, 0] + 2 * elev[0, 1] + elev[0, 2])) / (8 * res_m)
            slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
            return float(np.degrees(slope_rad))
        except Exception:
            return None

    def check(self, lat: float, lon: float) -> dict:
        result = {"lat": lat, "lon": lon, "feasible": True, "reasons": []}

        if not self.is_on_land(lat, lon):
            result["feasible"] = False
            result["reasons"].append("NOT_ON_LAND")

        if self.is_in_water(lat, lon):
            result["feasible"] = False
            result["reasons"].append("IN_WATER_BODY")

        if self.is_in_protected_area(lat, lon):
            result["feasible"] = False
            result["reasons"].append("IN_PROTECTED_AREA")

        corine = self.get_corine_code(lat, lon)
        if corine and corine in INFEASIBLE_CORINE_CODES:
            result["feasible"] = False
            result["reasons"].append(f"INFEASIBLE_LAND_COVER (CORINE={corine})")
        result["corine_code"] = corine

        slope = self.get_slope(lat, lon)
        if slope is not None and slope > MAX_SLOPE_DEGREES:
            result["feasible"] = False
            result["reasons"].append(f"SLOPE_TOO_STEEP ({slope:.1f}°)")
        result["slope_degrees"] = slope

        return result

    def filter_candidates(self, candidates: list[tuple[float, float]]) -> list[dict]:
        return [self.check(lat, lon) for lat, lon in candidates]

    def close(self):
        if self._dem_dataset:
            self._dem_dataset.close()
