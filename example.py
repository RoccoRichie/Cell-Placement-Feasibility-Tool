"""Example usage of the cell placement feasibility checker."""
from src.feasibility import FeasibilityChecker

# Sample candidate locations across Ireland
candidates = [
    # --- Should PASS ---
    (51.8986, -8.4706),   # Cork city — urban area
    (53.3498, -6.2603),   # Dublin city centre
    (52.6638, -8.6267),   # Limerick city
    (52.2593, -7.1128),   # Waterford city
    (54.2766, -8.4761),   # Sligo town
    (53.2707, -9.0568),   # Galway city
    # --- Should FAIL ---
    (51.5000, -9.9000),   # Atlantic Ocean off Mizen Head
    (51.7000, -10.2000),  # Skellig Michael area (ocean)
    (51.9930, -9.5400),   # Lough Leane, Killarney (lake)
    (53.4800, -9.1700),   # Lough Corrib (lake)
    (52.0150, -9.5050),   # Killarney National Park (protected)
    (53.2400, -7.6000),   # Clara Bog, Offaly (peat bog)
]

checker = FeasibilityChecker()

print("=" * 70)
print("CELL PLACEMENT FEASIBILITY REPORT — Ireland")
print("=" * 70)

results = checker.filter_candidates(candidates)

feasible = [r for r in results if r["feasible"]]
rejected = [r for r in results if not r["feasible"]]

for r in results:
    status = "✅ FEASIBLE" if r["feasible"] else "❌ REJECTED"
    print(f"\n  ({r['lat']:.4f}, {r['lon']:.4f}) — {status}")
    if r["reasons"]:
        for reason in r["reasons"]:
            print(f"    ↳ {reason}")
    if r["corine_code"]:
        print(f"    CORINE code: {r['corine_code']}")
    if r["slope_degrees"] is not None:
        print(f"    Slope: {r['slope_degrees']:.1f}°")

print(f"\n{'=' * 70}")
print(f"Summary: {len(feasible)}/{len(results)} candidates feasible")
print(f"{'=' * 70}")

checker.close()
