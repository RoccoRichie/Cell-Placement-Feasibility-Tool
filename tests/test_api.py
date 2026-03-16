"""API integration tests."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.feasibility import FeasibilityChecker
import src.api as api_module


def _make_test_app(checker: FeasibilityChecker) -> FastAPI:
    """Create a test app that skips lifespan and uses the given checker."""
    app = FastAPI(title="Cell Placement Feasibility API (test)")
    api_module.checker = checker

    # Re-register the routes on the test app
    app.get("/health")(api_module.health)
    app.get("/ready")(api_module.ready)
    app.post("/reload")(api_module.reload)
    app.get("/check")(api_module.check)
    app.post("/check/batch")(api_module.check_batch)
    return app


@pytest.fixture
def client(tmp_data_dir):
    """Create a test client with synthetic data."""
    checker = FeasibilityChecker(data_dir=tmp_data_dir, eager=True)
    app = _make_test_app(checker)
    with TestClient(app) as c:
        yield c
    checker.close()


@pytest.fixture
def empty_client(tmp_path):
    """Create a test client with no data (unhealthy state)."""
    checker = FeasibilityChecker(data_dir=str(tmp_path), eager=True)
    app = _make_test_app(checker)
    with TestClient(app) as c:
        yield c
    checker.close()


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_200_when_healthy(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["healthy"] is True
        assert "layers" in body

    def test_health_returns_503_when_unhealthy(self, empty_client):
        resp = empty_client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["healthy"] is False

    def test_health_lists_all_layers(self, client):
        body = client.get("/health").json()
        assert "ireland_boundary.geojson" in body["layers"]
        assert "water_bodies.geojson" in body["layers"]
        assert "protected_areas.geojson" in body["layers"]
        assert "copernicus_dem.tif" in body["layers"]


class TestReadyEndpoint:
    """Tests for GET /ready."""

    def test_ready_returns_200_when_ready(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_ready_returns_503_when_not_ready(self, empty_client):
        resp = empty_client.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["ready"] is False


class TestReloadEndpoint:
    """Tests for POST /reload."""

    def test_reload_returns_health_status(self, client):
        resp = client.post("/reload")
        assert resp.status_code == 200
        body = resp.json()
        assert "healthy" in body
        assert "layers" in body


class TestCheckEndpoint:
    """Tests for GET /check."""

    def test_feasible_location_returns_true(self, client):
        resp = client.get("/check", params={"lat": 52.0, "lon": -8.5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["feasible"] is True
        assert body["reasons"] == []
        assert body["lat"] == 52.0
        assert body["lon"] == -8.5

    def test_ocean_location_returns_rejected(self, client):
        resp = client.get("/check", params={"lat": 50.0, "lon": -12.0})
        assert resp.status_code == 200
        body = resp.json()
        assert body["feasible"] is False
        assert "NOT_ON_LAND" in body["reasons"]

    def test_lake_location_returns_rejected(self, client):
        resp = client.get("/check", params={"lat": 52.55, "lon": -7.95})
        assert resp.status_code == 200
        body = resp.json()
        assert body["feasible"] is False
        assert "IN_WATER_BODY" in body["reasons"]

    def test_protected_area_returns_rejected(self, client):
        resp = client.get("/check", params={"lat": 52.05, "lon": -9.45})
        assert resp.status_code == 200
        body = resp.json()
        assert body["feasible"] is False
        assert "IN_PROTECTED_AREA" in body["reasons"]

    def test_bog_location_returns_rejected(self, client):
        resp = client.get("/check", params={"lat": 53.05, "lon": -7.45})
        assert resp.status_code == 200
        body = resp.json()
        assert body["feasible"] is False
        assert any("INFEASIBLE_LAND_COVER" in r for r in body["reasons"])

    def test_missing_lat_returns_422(self, client):
        resp = client.get("/check", params={"lon": -8.0})
        assert resp.status_code == 422

    def test_missing_lon_returns_422(self, client):
        resp = client.get("/check", params={"lat": 52.0})
        assert resp.status_code == 422

    def test_missing_both_params_returns_422(self, client):
        resp = client.get("/check")
        assert resp.status_code == 422


class TestBatchEndpoint:
    """Tests for POST /check/batch."""

    def test_batch_mixed_results(self, client):
        payload = {
            "locations": [
                {"lat": 52.0, "lon": -8.5},    # feasible
                {"lat": 50.0, "lon": -12.0},   # ocean
                {"lat": 52.55, "lon": -7.95},  # lake
            ]
        }
        resp = client.post("/check/batch", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["feasible"] == 1
        assert body["rejected"] == 2
        assert len(body["results"]) == 3

    def test_batch_all_feasible(self, client):
        payload = {
            "locations": [
                {"lat": 52.0, "lon": -8.5},
                {"lat": 53.0, "lon": -8.0},
            ]
        }
        resp = client.post("/check/batch", json=payload)
        body = resp.json()
        assert body["feasible"] == 2
        assert body["rejected"] == 0

    def test_batch_all_rejected(self, client):
        payload = {
            "locations": [
                {"lat": 50.0, "lon": -12.0},
                {"lat": 52.55, "lon": -7.95},
            ]
        }
        resp = client.post("/check/batch", json=payload)
        body = resp.json()
        assert body["feasible"] == 0
        assert body["rejected"] == 2

    def test_batch_empty_list(self, client):
        resp = client.post("/check/batch", json={"locations": []})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0

    def test_batch_invalid_body_returns_422(self, client):
        resp = client.post("/check/batch", json={"locations": [{"lat": "abc"}]})
        assert resp.status_code == 422
