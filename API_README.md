# API Documentation — Cell Placement Feasibility

REST API for validating telecom cell placement locations against geospatial exclusion data.

## Data Sources

The API relies on geospatial data downloaded by `python -m src.fetch_data`:

| Layer | Source | Download |
|-------|--------|----------|
| Ireland land boundary | [Natural Earth](https://www.naturalearthdata.com/) | Automatic |
| Water bodies (lakes, rivers) | [Geofabrik OSM extract](https://download.geofabrik.de/europe/ireland-and-northern-ireland.html) | Automatic |
| Protected areas (reserves, parks) | [Geofabrik OSM extract](https://download.geofabrik.de/europe/ireland-and-northern-ireland.html) | Automatic |
| CORINE land cover | [Copernicus](https://land.copernicus.eu/pan-european/corine-land-cover) | Manual |
| DEM elevation | [Copernicus DEM GLO-30](https://registry.opendata.aws/copernicus-dem/) | Automatic |

## Running the API

```bash
cd cell-placement-tool
source venv/bin/activate
uvicorn src.api:app --host 0.0.0.0 --port 11011
```

The API loads all geospatial data into memory on startup. You'll see:

```
INFO:     Loading geospatial data into memory...
INFO:     Geospatial data loaded in 3.2s — API ready
```

## Interactive Documentation

- Swagger UI: [http://localhost:11011/docs](http://localhost:11011/docs)
- ReDoc: [http://localhost:11011/redoc](http://localhost:11011/redoc)

## Endpoints

### GET /health

Health check. Returns per-layer status and overall health. Returns HTTP 200 if all required layers are loaded, HTTP 503 if not.

```bash
curl http://localhost:11011/health
```

```json
{
  "healthy": true,
  "layers": {
    "ireland_boundary.geojson": {"status": "loaded", "features": 1},
    "water_bodies.geojson": {"status": "loaded", "features": 4832},
    "protected_areas.geojson": {"status": "loaded", "features": 312},
    "corine_clc.gpkg": {"status": "missing", "required": false},
    "copernicus_dem.tif": {"status": "missing", "required": false}
  }
}
```

Use this for liveness probes. The `healthy` field is `true` when all three required layers (land boundary, water bodies, protected areas) are loaded. Optional layers (CORINE, DEM) don't affect health status.

---

### GET /ready

Readiness probe. Returns HTTP 200 only when the API is fully initialised and can serve requests. Returns HTTP 503 during startup or if required data is missing.

```bash
curl http://localhost:11011/ready
```

```json
{"ready": true}
```

Use this for:
- Kubernetes readiness probes
- Load balancer health checks
- Client startup checks before sending traffic

---

### POST /reload

Force reload all geospatial layers from disk. Use after updating data files without restarting the API.

```bash
curl -X POST http://localhost:11011/reload
```

Returns the health status after reload.

---

### GET /check

Check feasibility of a single location.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| lat | float | Yes | Latitude (WGS84) |
| lon | float | Yes | Longitude (WGS84) |

```bash
curl "http://localhost:11011/check?lat=51.8969&lon=-8.4863"
```

**Feasible response:**

```json
{
  "lat": 51.8969,
  "lon": -8.4863,
  "feasible": true,
  "reasons": [],
  "corine_code": null,
  "slope_degrees": null
}
```

**Rejected response:**

```json
{
  "lat": 51.5,
  "lon": -9.9,
  "feasible": false,
  "reasons": ["NOT_ON_LAND"],
  "corine_code": null,
  "slope_degrees": null
}
```

---

### POST /check/batch

Check multiple locations in a single request.

```bash
curl -X POST http://localhost:11011/check/batch \
  -H "Content-Type: application/json" \
  -d '{"locations": [{"lat": 51.89, "lon": -8.48}, {"lat": 51.5, "lon": -9.9}]}'
```

```json
{
  "total": 2,
  "feasible": 1,
  "rejected": 1,
  "results": [...]
}
```

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| lat | float | Input latitude |
| lon | float | Input longitude |
| feasible | boolean | `true` if location passes all checks |
| reasons | string[] | Rejection reasons (empty if feasible) |
| corine_code | int / null | CORINE land cover code (null if data not installed) |
| slope_degrees | float / null | Terrain slope in degrees (null if DEM not installed) |

## Rejection Reasons

| Reason | Meaning |
|--------|---------|
| `NOT_ON_LAND` | In the ocean or outside Ireland boundary |
| `IN_WATER_BODY` | In a lake, river, or reservoir |
| `IN_PROTECTED_AREA` | In a SAC, SPA, or nature reserve |
| `INFEASIBLE_LAND_COVER (CORINE=XXX)` | Bog, marsh, estuary, etc. |
| `SLOPE_TOO_STEEP (XX.X°)` | Terrain slope exceeds 20° |

## Health Check Integration

### TypeScript client with retry

```typescript
const API_URL = "http://localhost:11011";

async function waitForApi(timeout = 60000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const resp = await fetch(`${API_URL}/ready`);
      if (resp.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("API not ready");
}

async function isFeasible(lat: number, lon: number): Promise<boolean> {
  const resp = await fetch(`${API_URL}/check?lat=${lat}&lon=${lon}`);
  const data = await resp.json();
  return data.feasible;
}

async function checkBatch(
  locations: { lat: number; lon: number }[]
): Promise<{ total: number; feasible: number; rejected: number; results: any[] }> {
  const resp = await fetch(`${API_URL}/check/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ locations }),
  });
  return resp.json();
}
```

### Python client with retry

```python
import requests
import time

API_URL = "http://localhost:11011"

def wait_for_api(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{API_URL}/ready", timeout=2)
            if resp.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    raise TimeoutError("API not ready")

def is_feasible(lat, lon):
    resp = requests.get(f"{API_URL}/check", params={"lat": lat, "lon": lon})
    return resp.json()["feasible"]
```

### Kubernetes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 11011
  initialDelaySeconds: 10
  periodSeconds: 30
readinessProbe:
  httpGet:
    path: /ready
    port: 11011
  initialDelaySeconds: 5
  periodSeconds: 10
```