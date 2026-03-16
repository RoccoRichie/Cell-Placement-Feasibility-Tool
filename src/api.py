"""REST API for cell placement feasibility checking."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.feasibility import FeasibilityChecker

logger = logging.getLogger("uvicorn.error")
checker: FeasibilityChecker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global checker
    logger.info("Loading geospatial data into memory...")
    start = time.time()
    checker = FeasibilityChecker(eager=True)
    health = checker.health()
    if health["healthy"]:
        logger.info(f"Geospatial data loaded in {time.time() - start:.1f}s — API ready")
    else:
        logger.warning(f"API started with missing layers — check GET /health")
    yield
    checker.close()


app = FastAPI(title="Cell Placement Feasibility API", lifespan=lifespan)


class LocationRequest(BaseModel):
    lat: float
    lon: float


class BatchRequest(BaseModel):
    locations: list[LocationRequest]


@app.get("/health")
def health():
    """
    Health check. Returns layer-by-layer status.
    HTTP 200 if all required layers are loaded, 503 otherwise.
    """
    status = checker.health()
    code = 200 if status["healthy"] else 503
    return JSONResponse(content=status, status_code=code)


@app.get("/ready")
def ready():
    """
    Readiness probe. Returns 200 only when the API can serve feasibility checks.
    Use this for load balancer / Kubernetes readiness probes.
    """
    if checker is None:
        return JSONResponse(content={"ready": False, "reason": "initialising"}, status_code=503)
    status = checker.health()
    if status["healthy"]:
        return {"ready": True}
    return JSONResponse(content={"ready": False, "reason": "missing_required_layers", "details": status["layers"]}, status_code=503)


@app.post("/reload")
def reload():
    """Force reload all geospatial layers. Use if data files were updated."""
    checker.reload()
    return checker.health()


@app.get("/check")
def check(lat: float = Query(...), lon: float = Query(...)):
    """Check feasibility of a single location. GET /check?lat=51.89&lon=-8.48"""
    return checker.check(lat, lon)


@app.post("/check/batch")
def check_batch(req: BatchRequest):
    """Check feasibility of multiple locations."""
    results = checker.filter_candidates([(loc.lat, loc.lon) for loc in req.locations])
    return {
        "total": len(results),
        "feasible": sum(1 for r in results if r["feasible"]),
        "rejected": sum(1 for r in results if not r["feasible"]),
        "results": results,
    }
