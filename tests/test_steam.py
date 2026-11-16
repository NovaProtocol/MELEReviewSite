"""Steam tables: the numbers have to match a printed table, and the chart has a
dome for every axis pair."""

from __future__ import annotations


def test_saturation_at_100c_matches_the_book(admin_client):
    row = admin_client.get(
        "/api/tools/steam/table",
        params={"basis": "temperature", "start": 100, "stop": 100, "count": 2},
    )
    assert row.status_code == 422, "two equal ends are not a range"

    table = admin_client.get(
        "/api/tools/steam/table",
        params={"basis": "temperature", "start": 99, "stop": 101, "count": 3},
    ).json()
    middle = table["rows"][1]
    assert abs(middle["T_sat"] - 100) < 0.05
    assert abs(middle["P_sat"] - 0.1014) < 0.002
    assert abs(middle["h_f"] - 419.2) < 1.5
    assert abs(middle["h_g"] - 2675.6) < 1.5
    assert abs(middle["s_f"] - 1.307) < 0.01
    assert abs(middle["h_fg"] - (middle["h_g"] - middle["h_f"])) < 1e-9


def test_saturation_by_pressure_starts_at_the_triple_point(admin_client):
    table = admin_client.get(
        "/api/tools/steam/table",
        params={"basis": "pressure", "start": 0.1, "stop": 1.0, "count": 3},
    ).json()
    assert len(table["rows"]) == 3
    assert abs(table["rows"][-1]["T_sat"] - 179.9) < 0.3


def test_a_range_through_the_critical_point_stops_and_says_so(admin_client):
    """There is no liquid and vapour above the critical point, so the table ends
    there rather than printing rows that mean nothing."""
    body = admin_client.get(
        "/api/tools/steam/table",
        params={"basis": "temperature", "start": 300, "stop": 500, "count": 5},
    ).json()
    assert body["truncated"] is True
    assert body["rows"][-1]["T_sat"] < 373.95


def test_a_range_entirely_above_the_critical_point_is_refused(admin_client):
    response = admin_client.get(
        "/api/tools/steam/table",
        params={"basis": "temperature", "start": 400, "stop": 500, "count": 5},
    )
    assert response.status_code == 422


def test_a_superheated_state(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    result = admin_client.post(
        "/api/tools/steam/state",
        json={"pressure": 1.0, "temperature": 300},
        headers={"X-CSRF-Token": token},
    ).json()
    state = result["state"]
    assert state["phase"] == "superheated vapour"
    assert abs(state["h"] - 3051.6) < 2
    assert abs(state["s"] - 7.1246) < 0.01
    assert abs(state["T"] - 300) < 1e-6


def test_a_mixture_from_pressure_and_quality(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    result = admin_client.post(
        "/api/tools/steam/state",
        json={"pressure": 0.1, "quality": 0.9},
        headers={"X-CSRF-Token": token},
    ).json()
    state = result["state"]
    assert abs(state["T"] - 99.6) < 0.3
    assert abs(state["h"] - 2449) < 4
    assert state["x"] == 0.9


def test_a_compressed_liquid(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    state = admin_client.post(
        "/api/tools/steam/state",
        json={"pressure": 10.0, "temperature": 100},
        headers={"X-CSRF-Token": token},
    ).json()["state"]
    assert state["phase"] == "compressed liquid"
    assert abs(state["v"] - 0.001038) < 2e-5


def test_quality_outside_zero_to_one_is_refused(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    response = admin_client.post(
        "/api/tools/steam/state",
        json={"pressure": 1.0, "quality": 1.4},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 422


def test_the_dome_is_a_full_liquid_and_vapour_curve_for_every_axis_pair(admin_client):
    dome = admin_client.get("/api/tools/steam/dome").json()["dome"]
    for kind in ("t-s", "h-s", "p-h"):
        assert len(dome[kind]["liquid_x"]) > 100
        assert len(dome[kind]["liquid_x"]) == len(dome[kind]["liquid_y"])
        assert len(dome[kind]["vapour_x"]) == len(dome[kind]["liquid_x"])
    # The two branches start far apart and meet at the critical point.
    assert dome["t-s"]["vapour_x"][0] - dome["t-s"]["liquid_x"][0] > 4
    # They meet at the critical point, which is where the sampling stops.
    width = dome["t-s"]["vapour_x"][0] - dome["t-s"]["liquid_x"][0]
    assert abs(dome["t-s"]["vapour_x"][-1] - dome["t-s"]["liquid_x"][-1]) < 0.05 * width
    assert dome["t-s"]["liquid_y"][-1] > 370


def test_the_dome_and_the_point_share_their_units(admin_client):
    """The chart places the point on the dome; SI against display units would put
    a state at 300 C a hundredfold off the page."""
    token = admin_client.cookies.get("melereview_csrf")
    dome = admin_client.get("/api/tools/steam/dome").json()["dome"]["t-s"]
    state = admin_client.post(
        "/api/tools/steam/state",
        json={"pressure": 1.0, "temperature": 300},
        headers={"X-CSRF-Token": token},
    ).json()

    assert max(dome["liquid_y"]) < 400, "temperatures are Celsius, not kelvin"
    assert max(dome["liquid_x"]) < 12, "entropy is kJ, not J"
    point = state["charts"]["t-s"]
    assert min(dome["liquid_x"]) < point["x"] < max(dome["vapour_x"])
    assert point["y"] == 300


def test_the_state_carries_a_point_for_each_chart(admin_client):
    token = admin_client.cookies.get("melereview_csrf")
    result = admin_client.post(
        "/api/tools/steam/state",
        json={"pressure": 1.0, "temperature": 300},
        headers={"X-CSRF-Token": token},
    ).json()
    for kind in ("t-s", "h-s", "p-h"):
        assert kind in result["charts"]
        assert set(result["charts"][kind]) == {"x", "y"}


def test_the_steam_tool_is_in_the_rail(admin_client):
    page = admin_client.get("/tools/steam")
    assert page.status_code == 200
    catalogue = admin_client.get("/library").text
    assert "Steam tables" in catalogue or "steam" in catalogue


def test_a_table_asked_from_zero_starts_at_the_triple_point(admin_client):
    body = admin_client.get(
        "/api/tools/steam/table",
        params={"basis": "temperature", "start": 0, "stop": 100, "count": 11},
    ).json()
    assert body["clamped"] is True
    assert body["rows"][0]["T_sat"] > 0.0
    assert len(body["rows"]) == 11
