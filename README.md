# Cell Placement Feasibility Tool — Ireland

Validates telecom cell placement locations against geospatial data to prevent placement in infeasible locations such as lakes, ocean, bogs, protected areas, and steep terrain.

## Prerequisites

- Python 3.10+
- pip

## Installation

### 1. Create a Python virtual environment

```bash
git clone https://github.com/<your-org>/cell-placement-tool.git
cd cell-placement-tool

python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Download geospatial data

```bash
python -m src.fetch_data
```

This automatically downloads:
- Ireland land boundary from [Natural Earth](https://www.naturalearthdata.com/) (~5MB)
- Ireland OpenStreetMap extract from [Geofabrik](https://download.geofabrik.de/europe/ireland-and-northern-ireland.html) (~80MB, one-time download)
  - Water bodies (lakes, rivers, reservoirs) are extracted locally from this file
  - Protected areas (nature reserves, national parks) are extracted locally from this file

All data is saved to the `data/` directory. No API rate limits — just reliable file downloads.

The fetch script also automatically downloads Copernicus DEM GLO-30 tiles for Ireland from [AWS Open Data](https://registry.opendata.aws/copernicus-dem/) (no registration needed, ~30m resolution) and merges them for slope analysis.

### 4. Optional: manual data download

This dataset improves accuracy but requires free registration on [Copernicus](https://land.copernicus.eu/). Without it, the tool still checks land boundary, water bodies, protected areas, and slope. Adding CORINE enables land cover classification (bog/marsh rejection).

| Dataset | Source | Place in |
|---------|--------|----------|
| CORINE Land Cover 2018 | [Copernicus](https://land.copernicus.eu/pan-european/corine-land-cover) | `data/corine_clc.gpkg` |

#### CORINE Land Cover 2018

1. Go to https://land.copernicus.eu/pan-european/corine-land-cover/clc2018
2. Create a free Copernicus account if you don't have one (email + password)
3. Once logged in, click "Download" on the CLC 2018 dataset
4. Choose the GeoPackage format (`.gpkg`) — shapefile also works
5. Select coverage area — full European dataset or clipped to Ireland
6. Download and place the file at:

```bash
cp ~/Downloads/clc2018.gpkg data/corine_clc.gpkg
```

This provides land classification codes for every polygon in Ireland. The tool rejects codes 411–523 (marshes, bogs, water courses, estuaries, etc.).

#### Verify the dataset is picked up

After placing the files, either:

- Re-run `python -m src.fetch_data` — steps 4/5 will show `✅` instead of `⚠️`
- Or if the API is already running, reload without restarting:

```bash
curl -X POST http://localhost:11011/reload
curl http://localhost:11011/health
```

Both datasets should show `"status": "loaded"` in the health check response.

## Usage

### Start the API server

```bash
source venv/bin/activate
uvicorn src.api:app --host 0.0.0.0 --port 11011
```

See [API_README.md](API_README.md) for full API documentation.

### TypeScript usage

```typescript
const API_URL = "http://localhost:11011";

async function isFeasible(lat: number, lon: number): Promise<boolean> {
  const resp = await fetch(`${API_URL}/check?lat=${lat}&lon=${lon}`);
  const data: { feasible: boolean; reasons: string[] } = await resp.json();
  return data.feasible;
}

// Usage
const ok = await isFeasible(51.8969, -8.4863);
console.log(ok); // true
```

### Python usage (without API)

```python
from src.feasibility import FeasibilityChecker

checker = FeasibilityChecker()
result = checker.check(lat=51.8969, lon=-8.4863)
print(result["feasible"])  # True
print(result["reasons"])   # []
```

## Feasibility Checks

| # | Check | Data Source | Rejects |
|---|-------|------------|---------|
| 1 | Land boundary | [Natural Earth](https://www.naturalearthdata.com/) (auto) | Ocean, offshore locations |
| 2 | Water bodies | [Geofabrik OSM extract](https://download.geofabrik.de/europe/ireland-and-northern-ireland.html) (auto) | Lakes, rivers, reservoirs |
| 3 | Protected areas | [Geofabrik OSM extract](https://download.geofabrik.de/europe/ireland-and-northern-ireland.html) (auto) | Nature reserves, national parks, forests |
| 4 | CORINE land cover | [Copernicus](https://land.copernicus.eu/pan-european/corine-land-cover) (manual) | Bogs, marshes, estuaries, intertidal flats (codes 411–523) |
| 5 | Slope analysis | [Copernicus DEM GLO-30](https://registry.opendata.aws/copernicus-dem/) (auto) | Terrain steeper than 20° |

## Project Structure

```
cell-placement-tool/
├── data/                  # Downloaded geospatial data
├── src/
│   ├── api.py             # FastAPI REST API
│   ├── feasibility.py     # Core feasibility checker
│   └── fetch_data.py      # Data download script
├── example.py             # Demo with sample locations
├── requirements.txt
├── README.md              # This file
└── API_README.md          # API documentation
```

## Deactivating the virtual environment

```bash
deactivate
```
