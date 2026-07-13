# QuantaRoute Quantum / QUBO Experiment Readiness Report

## Executive Summary

QuantaRoute is ready to export route optimisation problems for external solver
experiments, provided the experiment layer is kept outside the live production
route path by default.

The current production optimiser is already structured around a clean route
problem:

- cleaned stop addresses
- geocoded coordinates
- a road-distance matrix in kilometres
- candidate route orders as integer indices into that matrix
- benchmark distances for input order, nearest-neighbour, and final selected
  route
- an `algorithm_used` string surfaced through the public API, saved route
  history, and route sheets

The safest next step is not to enable QAOA or call an external API in live
requests. The safe next step is to add a small, offline export helper or
flag-gated internal function that serialises the route-distance matrix and
metadata to JSON for manual Strangeworks/QUBO experiments.

## Current Production Flow

Production optimisation currently lives in `backend/services/route_builder.py`.
The key path is:

1. Clean input addresses.
2. Geocode delivery stops with `geocode_addresses`.
3. Build a delivery-stop distance matrix with `build_distance_matrix`.
4. Select the production route order:
   - fewer than 8 geocoded stops: exact brute force
   - 8 or more geocoded stops: nearest-neighbour heuristic
5. Geocode optional start/end boundary addresses.
6. Build a combined matrix including optional start/end points for distance
   reporting.
7. Compare input order, nearest-neighbour order, and final selected order.
8. Build Google Maps and WhatsApp URLs.
9. Return `algorithm_used` in the API result and persist it to route history.

`backend/services/qaoa.py` contains Qiskit/QAOA utilities, including TSP to
QUBO conversion, but `route_builder.py` does not call the QAOA entry point in
production. That is the right safety posture.

## Architecture Diagram

```text
User / API / MCP request
        |
        v
backend/main.py
        |
        v
route_builder.optimise_route(...)
        |
        +--> clean_route_address(...)
        |
        +--> geocoder.geocode_addresses(...)
        |
        +--> road_matrix.build_distance_matrix(valid_coords)
        |          |
        |          +--> OSRM table API
        |          +--> Haversine fallback
        |
        +--> select_route_order(matrix, requested_stops_count)
        |          |
        |          +--> n < 8: brute_force_route(matrix)
        |          +--> n >= 8: nearest_neighbour_route(matrix)
        |
        +--> benchmark distances
        |          |
        |          +--> input order
        |          +--> nearest-neighbour
        |          +--> final selected route
        |
        +--> production response + route history
                   |
                   +--> algorithm_used
                   +--> route sheet

Experimental path, disabled by default:

route_builder/export helper
        |
        v
route problem JSON
        |
        +--> offline notebook / script
        +--> Strangeworks-style QUBO/QAOA/hybrid API
        +--> local Qiskit experiment
        |
        v
solver result JSON
        |
        v
comparison report against brute force / nearest-neighbour
```

## Readiness Questions

### 1. Where is the distance matrix created?

The main delivery-stop matrix is created in `backend/services/route_builder.py`
by calling:

```python
matrix = build_distance_matrix(valid_coords)
```

The implementation is in `backend/services/road_matrix.py`:

```python
def build_distance_matrix(coordinates: list[tuple]) -> np.ndarray:
```

That function calls the OSRM table API and returns a NumPy `ndarray` of
kilometre distances. If OSRM fails or returns incomplete data, it falls back to
a Haversine matrix.

`route_builder.py` also creates a second `combined_matrix` after optional start
and end coordinates are known. That matrix is used for reporting full path
distances including depot/start and return/end points.

### 2. Is the distance matrix available in a clean format that could be exported?

Yes, but not yet as a first-class export object.

Internally it is a clean numeric NumPy `ndarray`. It can be exported safely with
`matrix.tolist()` plus address and coordinate metadata. The cleanest export
format should include:

- `addresses`
- `coordinates`
- `distance_matrix_km`
- `matrix_source`, such as `osrm_or_haversine_fallback`
- `start_address` and `end_address`, when present
- `problem_type`, such as `open_tsp_path` or `closed_tsp_cycle`
- baseline orders and distances

No production API currently exposes the matrix, which is good for reliability
and for avoiding accidental data/API surface expansion.

### 3. What exact data structure represents the route problem?

The route problem is represented by these structures:

- `addresses`: cleaned list of stop strings.
- `coords`: geocoder output, one `(lat, lng)` tuple or `None` per address.
- `valid_coords`: filtered list of valid `(lat, lng)` tuples.
- `valid_addresses`: address strings aligned with `valid_coords`.
- `matrix`: NumPy `ndarray` where `matrix[i][j]` is distance in km from stop
  index `i` to stop index `j`.
- `original_order`: `list[int]`, normally `[0, 1, 2, ...]`.
- `nn_order`: `list[int]`, output from `nearest_neighbour_route(matrix)`.
- `optimised_order`: `list[int]`, output from `select_route_order(...)`.

Optional start/end route boundaries are represented separately:

- `clean_start_address`
- `clean_end_address`
- `boundary_coords`
- `combined_coords`
- `combined_matrix`
- `delivery_path(order)`, which maps a delivery-only order into a full path
  containing start and/or end indices.

### 4. Can the current route problem be converted into TSP/QUBO format?

Yes.

For delivery stops only, the current `matrix` is already the core TSP cost
matrix. `backend/services/qaoa.py` demonstrates the conversion path:

```python
tsp = Tsp(matrix.astype(float))
qp = tsp.to_quadratic_program()
qubo = QuadraticProgramToQubo().convert(qp)
```

Important nuance: Qiskit's `Tsp(matrix)` models a cycle. QuantaRoute's live
courier flow is often an open path, especially when there is no return-to-start.
For external QUBO experiments, the payload should explicitly state whether the
problem is:

- `closed_tsp_cycle`: route returns to depot/start.
- `open_tsp_path`: route starts at a depot and ends at final delivery or
  explicit end address.
- `delivery_order_only`: optimise only the order of delivery stops, then score
  with start/end boundaries separately.

The minimum safe experiment should use `delivery_order_only` first, because it
matches the existing production selection boundary and is easiest to compare.

### 5. What would be the safest place to add an experimental solver hook?

The safest hook point is after `matrix = build_distance_matrix(valid_coords)`
and before or beside `select_route_order(matrix, len(addresses))` in
`route_builder.optimise_route`.

The hook should not replace production selection by default. A safe shape would
be:

```python
if optimisation_mode == "production":
    optimised_order, algorithm_used = select_route_order(matrix, len(addresses))
elif optimisation_mode == "experimental_qaoa":
    # explicit local tests only
elif optimisation_mode == "external_solver":
    # future stub/export only
```

Default must remain `optimisation_mode="production"` or
`experimental_solver=False`.

Even safer for the first iteration: do not add a runtime hook yet. Add an
offline export function or script that accepts addresses, geocodes them, builds
the matrix, and writes JSON without changing `/api/optimise-route`.

### 6. How should we avoid slowing or breaking production route requests?

Use these guardrails:

- Keep production default as brute force under 8 stops and nearest-neighbour at
  8 or more stops.
- Do not call QAOA or external solvers from normal web/API requests.
- Do not import heavy Qiskit or external solver SDKs on FastAPI startup.
- Put all external solver code behind an explicit flag or separate script.
- Use strict timeouts if a future API endpoint is added.
- Always fall back to current production result.
- Never block route sheet generation or public API response on experiments.
- Store experiment results as comparisons, not as the live route, until proven.

### 7. Should external solver experiments run synchronously, asynchronously, or offline?

Offline first.

Recommended progression:

1. Offline export and manual solver experiment.
2. Offline batch benchmark script against saved/sample routes.
3. Async background job for internal experiments only.
4. Synchronous request-time solver only if it has hard timeouts, excellent
   reliability, and clear value over the current route selectors.

For now, Strangeworks-style external solver experiments should not run inside
the public `/api/optimise-route` request.

### 8. What payload would we send to a Strangeworks-style API?

The safest initial payload is a route-distance matrix export, not raw customer
secrets. Addresses may still be sensitive, so experiments should support a
`redacted_addresses` mode.

Example export payload:

```json
{
  "schema_version": "quantaroute.route_matrix.v1",
  "problem_id": "qr-exp-2026-06-29-0001",
  "problem_type": "delivery_order_only",
  "objective": "minimise_total_distance_km",
  "units": "km",
  "source": "offline_export",
  "matrix_source": "osrm_or_haversine_fallback",
  "stops": [
    {
      "index": 0,
      "address": "Depot or Stop A, Plymouth",
      "lat": 50.3755,
      "lng": -4.1427
    },
    {
      "index": 1,
      "address": "Stop B, Plymouth",
      "lat": 50.3670,
      "lng": -4.1342
    },
    {
      "index": 2,
      "address": "Stop C, Plymouth",
      "lat": 50.3810,
      "lng": -4.1600
    }
  ],
  "distance_matrix_km": [
    [0.0, 2.4, 4.1],
    [2.5, 0.0, 3.2],
    [4.0, 3.4, 0.0]
  ],
  "constraints": {
    "visit_each_stop_once": true,
    "fixed_start_index": 0,
    "return_to_start": false,
    "max_runtime_seconds": 20
  },
  "baselines": {
    "input_order": {
      "order": [0, 1, 2],
      "distance_km": 5.6
    },
    "nearest_neighbour": {
      "order": [0, 1, 2],
      "distance_km": 5.6
    },
    "production_selected": {
      "order": [0, 1, 2],
      "distance_km": 5.6,
      "algorithm_used": "exact brute force"
    }
  }
}
```

For a QUBO-specific API, include either:

- the matrix plus a request for the provider to formulate TSP/QUBO, or
- an explicit QUBO object with variables, linear terms, quadratic terms, offset,
  and penalty weights.

The matrix-first payload is easier to audit and less likely to encode a bad
penalty model too early.

### 9. What result format would we expect back?

Expected solver result:

```json
{
  "schema_version": "quantaroute.solver_result.v1",
  "problem_id": "qr-exp-2026-06-29-0001",
  "solver": {
    "provider": "strangeworks",
    "backend": "example-hybrid-tsp",
    "method": "qubo_hybrid",
    "runtime_seconds": 8.42
  },
  "status": "success",
  "candidate": {
    "order": [0, 2, 1],
    "distance_km": 7.4,
    "feasible": true
  },
  "diagnostics": {
    "objective_value": 7.4,
    "constraint_violations": [],
    "raw_status": "completed"
  }
}
```

If the solver returns bitstrings or variable assignments, QuantaRoute should
decode them into the same `order: list[int]` shape before comparison.

### 10. How would we compare external solver results against brute force and nearest-neighbour?

Use the same scoring function as production:

- candidate route order: `list[int]`
- distance matrix: NumPy array or JSON matrix
- score: `calculate_path_distance(order, matrix)` for open path, or
  `calculate_total_distance(order, matrix)` for closed cycle

Comparison report example:

```json
{
  "schema_version": "quantaroute.solver_comparison.v1",
  "problem_id": "qr-exp-2026-06-29-0001",
  "stops_count": 6,
  "production": {
    "algorithm_used": "exact brute force",
    "order": [0, 3, 1, 4, 2, 5],
    "distance_km": 18.7
  },
  "baselines": {
    "input_order_distance_km": 22.1,
    "nearest_neighbour_order": [0, 1, 4, 2, 5, 3],
    "nearest_neighbour_distance_km": 19.4,
    "exact_brute_force_distance_km": 18.7
  },
  "external_solver": {
    "provider": "strangeworks",
    "method": "qubo_hybrid",
    "order": [0, 3, 1, 4, 2, 5],
    "distance_km": 18.7,
    "runtime_seconds": 8.42,
    "feasible": true
  },
  "deltas": {
    "external_vs_input_percent": 15.38,
    "external_vs_nearest_neighbour_percent": 3.61,
    "external_vs_production_percent": 0.0
  },
  "accepted_for_production": false
}
```

For fewer than 8 stops, brute force is the ground truth. For 8 or more stops,
nearest-neighbour is the current production baseline, and external solvers can
be compared as candidate improvements.

### 11. What route sizes are safe for experimentation?

Recommended safe ranges:

- 2 to 7 stops: safest correctness benchmark, because exact brute force is
  available as ground truth.
- 8 to 12 stops: useful early hybrid/QUBO experiments, compared against
  nearest-neighbour and sampled/local search baselines.
- 13 to 20 stops: possible offline only, with strict runtime and cost caps.
- More than 20 stops: out of current public API scope and not recommended until
  batching, constraints, and solver cost are better understood.

For QUBO/TSP, variable count grows roughly as `n * n`, before penalty terms.
Even small route-size increases can become expensive.

### 12. What timeouts/fallbacks should be used?

For production:

- keep current route selection immediate and local
- no external solver calls

For offline or internal experiments:

- 2 to 7 stops: 10 to 20 seconds per solver attempt
- 8 to 12 stops: 20 to 60 seconds per solver attempt
- 13 to 20 stops: async/offline only, explicit cost budget, 2 to 5 minute cap

For any future internal request-time experiment:

- use a hard timeout of 1 to 3 seconds
- return production route if the solver is late, invalid, or infeasible
- mark the experiment as `timed_out`, `failed`, or `not_used`
- never let the external result overwrite production without validation

### 13. What should `algorithm_used` show for experimental runs?

Production should remain:

- `exact brute force`
- `nearest-neighbour heuristic`
- `input order safety fallback after ...`

For explicit experimental runs only, use strings that are honest and auditable:

- `experimental local QAOA candidate; production fallback used`
- `external solver candidate; production fallback used`
- `external solver accepted in experimental mode`
- `external solver timed out; production nearest-neighbour used`

Do not show `Qiskit QAOA quantum simulation` in production unless the live route
was actually selected by that solver and the mode was explicitly experimental.

### 14. What database fields would be useful to store solver comparisons?

Do not add these fields until the export/comparison shape has stabilised.

When ready, prefer a separate experiment table over widening route history too
much:

```text
quantaroute_solver_experiments
  id
  created_at
  route_id nullable
  problem_id
  optimisation_mode
  solver_provider
  solver_backend
  solver_method
  stops_count
  problem_type
  production_algorithm_used
  production_order_json
  production_distance_km
  input_order_distance_km
  nearest_neighbour_order_json
  nearest_neighbour_distance_km
  exact_brute_force_distance_km nullable
  solver_order_json
  solver_distance_km
  solver_runtime_seconds
  solver_status
  solver_feasible
  delta_vs_production_percent
  delta_vs_nearest_neighbour_percent
  accepted_for_production boolean default false
  notes
```

For the existing route history table, the only near-term useful field would be
`optimisation_mode`, but even that can wait if experiments are offline.

### 15. What tests should be added?

Recommended tests before any experimental code path ships:

- Export helper returns JSON-serialisable lists, not NumPy arrays.
- Exported matrix dimensions match `stops_count`.
- Exported stops preserve index/address/coordinate alignment.
- Export helper rejects fewer than 2 geocoded stops.
- Production default does not call QAOA or external solver.
- `optimisation_mode="production"` preserves current algorithm behavior.
- `optimisation_mode="external_solver"` is rejected or stubbed unless an
  explicit experimental flag is true.
- Solver result validation rejects duplicate indices, missing indices, out of
  range indices, and non-finite distances.
- Candidate scoring uses the same distance function as production.
- Timeout/failure path returns the production route and records an experimental
  failure status.
- Public API response remains unchanged unless an explicit experimental endpoint
  or internal flag is used.
- Route sheet continues to show the production `algorithm_used`.

## Minimum Safe Next Step

Add a doc-backed, offline export script or helper that builds and writes a
route-matrix JSON file for a small known route, then compare a hand-supplied
solver result against production baselines.

Suggested scope:

1. Create `scripts/export_route_problem.py`.
2. Keep it offline/admin-only.
3. Use existing `geocode_addresses` and `build_distance_matrix`.
4. Write JSON with `distance_matrix_km`, stops, coordinates, and baselines.
5. Add tests for export shape and production-flow isolation.
6. Do not add external API calls, secrets, Render config, or production request
   hooks yet.

This gives QuantaRoute a research bridge to Strangeworks/QUBO experiments
without making live courier routing depend on quantum/hybrid solver latency,
availability, or result quality.

## Offline Export Helper

Use `scripts/export_route_problem.py` to create JSON payloads for future
Strangeworks/QUBO/QAOA experiments. This is for offline research/benchmarking
only. Production routing does not depend on external quantum solvers.

Demo export, with no database, secrets, geocoding calls, routing calls, or
external solver calls:

```powershell
python scripts/export_route_problem.py --demo --out exports/plymouth_route_problem.json
```

Saved route metadata export, using `DATABASE_URL` when configured and local
SQLite otherwise:

```powershell
python scripts/export_route_problem.py --route-id 123 --out exports/route_123_problem.json
```

Saved route history currently does not store the original distance matrix, so
`distance_matrix_km` is `null` for `--route-id` exports. Use `--demo` for a
complete static matrix export until matrix capture is added behind an explicit
experimental flag.
