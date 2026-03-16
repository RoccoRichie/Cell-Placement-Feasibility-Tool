"""Unit tests for FeasibilityChecker."""
import pytest
from src.feasibility import FeasibilityChecker


class TestIsOnLand:
    """Tests for land boundary check."""

    def test_point_on_land_is_feasible(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.is_on_land(52.0, -8.0) is True

    def test_point_in_ocean_is_not_on_land(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.is_on_land(50.0, -12.0) is False

    def test_point_on_boundary_edge(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        # Point just inside the southern boundary
        assert checker.is_on_land(51.5, -8.0) is True

    def test_no_data_defaults_to_on_land(self, tmp_path):
        checker = FeasibilityChecker(data_dir=str(tmp_path))
        assert checker.is_on_land(0.0, 0.0) is True


class TestIsInWater:
    """Tests for water body check."""

    def test_point_in_lake_detected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        # Centre of the test lake
        assert checker.is_in_water(52.55, -7.95) is True

    def test_point_outside_lake_not_detected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.is_in_water(52.0, -8.5) is False

    def test_no_data_defaults_to_not_in_water(self, tmp_path):
        checker = FeasibilityChecker(data_dir=str(tmp_path))
        assert checker.is_in_water(52.55, -7.95) is False


class TestIsInProtectedArea:
    """Tests for protected area check."""

    def test_point_in_reserve_detected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.is_in_protected_area(52.05, -9.45) is True

    def test_point_outside_reserve_not_detected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.is_in_protected_area(53.5, -7.0) is False

    def test_no_data_defaults_to_not_protected(self, tmp_path):
        checker = FeasibilityChecker(data_dir=str(tmp_path))
        assert checker.is_in_protected_area(52.05, -9.45) is False


class TestCorineCode:
    """Tests for CORINE land cover check."""

    def test_point_in_bog_returns_code(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.get_corine_code(53.05, -7.45) == 412

    def test_point_outside_corine_returns_none(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.get_corine_code(52.0, -8.0) is None

    def test_no_data_returns_none(self, tmp_path):
        checker = FeasibilityChecker(data_dir=str(tmp_path))
        assert checker.get_corine_code(53.05, -7.45) is None


class TestSlope:
    """Tests for slope check (no DEM in test fixtures)."""

    def test_no_dem_returns_none(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.get_slope(52.0, -8.0) is None


class TestCheck:
    """Tests for the combined check() method."""

    def test_feasible_location(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        result = checker.check(52.0, -8.5)
        assert result["feasible"] is True
        assert result["reasons"] == []
        assert result["lat"] == 52.0
        assert result["lon"] == -8.5

    def test_ocean_location_rejected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        result = checker.check(50.0, -12.0)
        assert result["feasible"] is False
        assert "NOT_ON_LAND" in result["reasons"]

    def test_lake_location_rejected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        result = checker.check(52.55, -7.95)
        assert result["feasible"] is False
        assert "IN_WATER_BODY" in result["reasons"]

    def test_protected_area_rejected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        result = checker.check(52.05, -9.45)
        assert result["feasible"] is False
        assert "IN_PROTECTED_AREA" in result["reasons"]

    def test_bog_location_rejected(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        result = checker.check(53.05, -7.45)
        assert result["feasible"] is False
        assert any("INFEASIBLE_LAND_COVER" in r for r in result["reasons"])
        assert result["corine_code"] == 412

    def test_multiple_rejection_reasons(self, tmp_data_dir):
        """A point in the ocean should not be on land (may also trigger other checks)."""
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        result = checker.check(50.0, -12.0)
        assert result["feasible"] is False
        assert len(result["reasons"]) >= 1


class TestFilterCandidates:
    """Tests for batch filtering."""

    def test_mixed_candidates(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        candidates = [
            (52.0, -8.5),    # on land, clear
            (50.0, -12.0),   # ocean
            (52.55, -7.95),  # lake
        ]
        results = checker.filter_candidates(candidates)
        assert len(results) == 3
        assert results[0]["feasible"] is True
        assert results[1]["feasible"] is False
        assert results[2]["feasible"] is False

    def test_empty_candidates(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir)
        assert checker.filter_candidates([]) == []


class TestHealth:
    """Tests for health check."""

    def test_healthy_with_all_required_layers(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir, eager=True)
        status = checker.health()
        assert status["healthy"] is True
        assert status["layers"]["ireland_boundary.geojson"]["status"] == "loaded"
        assert status["layers"]["water_bodies.geojson"]["status"] == "loaded"
        assert status["layers"]["protected_areas.geojson"]["status"] == "loaded"

    def test_unhealthy_with_no_data(self, tmp_path):
        checker = FeasibilityChecker(data_dir=str(tmp_path), eager=True)
        status = checker.health()
        assert status["healthy"] is False

    def test_optional_layers_dont_affect_health(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir, eager=True)
        status = checker.health()
        # DEM is missing but health is still True
        assert status["healthy"] is True
        assert status["layers"]["copernicus_dem.tif"]["status"] == "missing"


class TestReload:
    """Tests for reload / self-healing."""

    def test_reload_restores_layers(self, tmp_data_dir):
        checker = FeasibilityChecker(data_dir=tmp_data_dir, eager=True)
        # Simulate corruption by clearing a layer
        checker._water = None
        assert checker.health()["layers"]["water_bodies.geojson"]["status"] != "loaded"
        # Reload should fix it
        checker.reload()
        assert checker.health()["layers"]["water_bodies.geojson"]["status"] == "loaded"
