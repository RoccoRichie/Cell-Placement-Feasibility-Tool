"""Example usage of the cell placement feasibility checker."""
from src.feasibility import FeasibilityChecker

# Sample candidate locations in southern Ireland
candidates = [
    (51.8969, -8.4863),   # Cork city centre — should PASS
    (51.7700, -9.7500),   # Kenmare Bay (ocean) — should FAIL
    (51.9500, -9.5700),   # Lough Leane, Killarney — should FAIL (lake)
    (52.0600, -9.5100),   # Killarney National Park — should FAIL (protected)
    (51.8500, -8.3000),   # Rural area east of Cork — should PASS
    (51.5000, -9.9000),   # Atlantic Ocean off Mizen Head — should FAIL
    (52.1400, -7.1100),   # Waterford area — should PASS
    (51.7000, -10.2000),  # Skellig Michael area (ocean) — should FAIL
]

checker = FeasibilityChecker()

print("=" * 70)
print("CELL PLACEMENT FEASIBILITY REPORT — Southern Ireland")
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
