import asyncio

import numpy as np

from backend.services import route_builder


def test_start_and_end_are_included_in_reported_distances(monkeypatch):
    async def fake_geocode_addresses(addresses):
        lookup = {
            "Depot": (0.0, 0.0),
            "Stop A": (0.0, 1.0),
            "Stop B": (0.0, 3.0),
            "End": (0.0, 4.0),
        }
        return [lookup.get(address) for address in addresses]

    def fake_build_distance_matrix(coords):
        matrix = np.zeros((len(coords), len(coords)))
        for i, coord_a in enumerate(coords):
            for j, coord_b in enumerate(coords):
                matrix[i][j] = abs(coord_a[1] - coord_b[1])
        return matrix

    monkeypatch.setattr(route_builder, "geocode_addresses", fake_geocode_addresses)
    monkeypatch.setattr(route_builder, "build_distance_matrix", fake_build_distance_matrix)

    result = asyncio.run(
        route_builder.optimise_route(
            addresses=["Stop A", "Stop B"],
            start_address="Depot",
            end_address="End",
        )
    )

    assert result["original_order_distance_km"] == 4.0
    assert result["final_selected_distance_km"] == 4.0
    assert result["total_distance_km"] == 4.0
    assert result["maps_url"].endswith("/Depot/Stop%20A/Stop%20B/End")


def test_eight_stop_live_pipeline_uses_nearest_neighbour_not_qaoa(monkeypatch):
    addresses = [f"Stop {index}" for index in range(8)]

    async def fake_geocode_addresses(input_addresses):
        lookup = {address: (0.0, float(index)) for index, address in enumerate(addresses)}
        return [lookup.get(address) for address in input_addresses]

    def fake_build_distance_matrix(coords):
        matrix = np.zeros((len(coords), len(coords)))
        for i, coord_a in enumerate(coords):
            for j, coord_b in enumerate(coords):
                matrix[i][j] = abs(coord_a[1] - coord_b[1])
        return matrix

    monkeypatch.setattr(route_builder, "geocode_addresses", fake_geocode_addresses)
    monkeypatch.setattr(route_builder, "build_distance_matrix", fake_build_distance_matrix)

    result = asyncio.run(route_builder.optimise_route(addresses=addresses))

    assert result["algorithm_used"] == "nearest-neighbour heuristic"
