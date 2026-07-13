import json

from scripts.export_route_problem import build_demo_export, main


def test_demo_export_contains_static_matrix_without_database(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    payload = build_demo_export()

    assert payload["source"] == "demo"
    assert payload["problem_id"] == "demo-plymouth-route-problem"
    assert payload["baseline_algorithm_used"] == "exact brute force"
    assert len(payload["stops"]) == 4
    assert len(payload["distance_matrix_km"]) == 4
    assert len(payload["distance_matrix_km"][0]) == 4
    assert payload["optimised_distance_km"] <= payload["original_distance_km"]
    assert "external quantum solvers" in payload["notes"][0]

    out_path = tmp_path / "plymouth_route_problem.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "export_route_problem.py",
            "--demo",
            "--out",
            str(out_path),
        ],
    )

    main()

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["problem_id"] == payload["problem_id"]
    assert written["distance_matrix_km"] == payload["distance_matrix_km"]
