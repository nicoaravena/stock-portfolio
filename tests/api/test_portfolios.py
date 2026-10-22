from decimal import Decimal

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

JSON = "application/json"


def _quantities(body: dict) -> dict[str, int]:
    return {h["stock"]["symbol"]: h["quantity"] for h in body["holdings"]}


def test_portfolio_create(client: Client, stocks):
    response = client.post(
        "/api/portfolios",
        {
            "name": "p",
            "holdings": [
                {"symbol": "a", "quantity": 3, "allocation": 50},
                {"symbol": "B", "allocation": 50},
            ],
        },
        JSON,
    )
    assert response.status_code == 201
    body = response.json()
    assert _quantities(body) == {"A": 3, "B": 0}
    assert Decimal(body["holdings"][0]["stock"]["last_price"]) == 1
    assert body["pending_plan"] is None


def test_portfolio_duplicate_name(client: Client, portfolio_id: int):
    response = client.post(
        "/api/portfolios",
        {"name": "p", "holdings": [{"symbol": "A", "allocation": 100}]},
        JSON,
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "holdings",
    [
        [{"symbol": "A", "quantity": 3, "allocation": 50}],
        [{"symbol": "A", "allocation": 50}, {"symbol": "a", "allocation": 50}],
        [{"symbol": "A", "allocation": 101}],
    ],
)
def test_portfolio_invalid_holdings(client: Client, stocks, holdings):
    response = client.post("/api/portfolios", {"name": "p", "holdings": holdings}, JSON)
    assert response.status_code == 422
    assert client.get("/api/portfolios").json() == []


def test_portfolio_unknown_stock(client: Client, stocks):
    response = client.post(
        "/api/portfolios",
        {"name": "p", "holdings": [{"symbol": "Z", "allocation": 100}]},
        JSON,
    )
    assert response.status_code == 404
    assert client.get("/api/portfolios").json() == []


def test_portfolio_update_and_delete(client: Client, portfolio_id: int):
    url = f"/api/portfolios/{portfolio_id}"
    client.post(f"{url}/rebalance", {"cash": "5"}, JSON)

    response = client.put(
        url,
        {"name": "q", "holdings": [{"symbol": "A", "quantity": 1, "allocation": 100}]},
        JSON,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "q"
    assert body["pending_plan"] is None
    assert _quantities(body) == {"A": 1}

    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_rebalance_and_execute_trades(client: Client, portfolio_id: int):
    url = f"/api/portfolios/{portfolio_id}"
    response = client.post(f"{url}/rebalance", {"cash": "5.0"}, JSON)
    assert response.status_code == 200
    plan = response.json()
    assert Decimal(plan["total_value"]) == 13
    assert Decimal(plan["cash_leftover"]) == 1
    [trade] = plan["trades"]
    assert (trade["symbol"], trade["action"], trade["quantity"]) == ("A", "BUY", 4)
    assert Decimal(trade["price"]) == 1
    assert client.get(url).json()["pending_plan"] == plan
    assert client.post(f"{url}/rebalance", {}, JSON).status_code == 409

    response = client.post(f"{url}/execute-trades")
    assert response.status_code == 200
    body = response.json()
    assert _quantities(body) == {"A": 7, "B": 2}
    assert Decimal(body["cash_leftover"]) == 1
    assert body["pending_plan"] is None

    assert client.post(f"{url}/execute-trades").status_code == 409


def test_rebalance_sells_unallocated_holding(client: Client, stocks):
    response = client.post(
        "/api/portfolios",
        {
            "name": "p",
            "holdings": [
                {"symbol": "A", "quantity": 5, "allocation": 100},
                {"symbol": "B", "quantity": 2},
            ],
        },
        JSON,
    )
    url = f"/api/portfolios/{response.json()['id']}"
    plan = client.post(f"{url}/rebalance", {}, JSON).json()
    trades = [(t["symbol"], t["action"], t["quantity"]) for t in plan["trades"]]
    assert trades == [("B", "SELL", 2), ("A", "BUY", 5)]

    body = client.post(f"{url}/execute-trades").json()
    assert _quantities(body) == {"A": 10, "B": 0}


def test_rebalance_too_much_cash_removed(client: Client, portfolio_id: int):
    response = client.post(
        f"/api/portfolios/{portfolio_id}/rebalance", {"cash": "-100"}, JSON
    )
    assert response.status_code == 422


def test_portfolio_list_and_get(client: Client, stocks):
    assert client.get("/api/portfolios").json() == []
    ids = [
        client.post(
            "/api/portfolios",
            {"name": name, "holdings": [{"symbol": "A", "allocation": 100}]},
            JSON,
        ).json()["id"]
        for name in ("z", "a")
    ]

    response = client.get("/api/portfolios")
    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == sorted(ids)

    body = client.get(f"/api/portfolios/{ids[1]}").json()
    assert body["name"] == "a"
    assert _quantities(body) == {"A": 0}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", ""),
        ("put", ""),
        ("delete", ""),
        ("post", "/rebalance"),
        ("post", "/execute-trades"),
    ],
)
def test_portfolio_not_found(client: Client, stocks, method: str, path: str):
    url = f"/api/portfolios/999{path}"
    if method in ("get", "delete"):
        response = getattr(client, method)(url)
    else:
        payload = {"name": "p", "holdings": [{"symbol": "A", "allocation": 100}]}
        response = getattr(client, method)(url, payload, JSON)
    assert response.status_code == 404


def test_portfolio_update_duplicate_name(client: Client, portfolio_id: int):
    client.post(
        "/api/portfolios",
        {"name": "q", "holdings": [{"symbol": "A", "allocation": 100}]},
        JSON,
    )
    response = client.put(
        f"/api/portfolios/{portfolio_id}",
        {"name": "q", "holdings": [{"symbol": "A", "allocation": 100}]},
        JSON,
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Portfolio q already exists"}
    assert client.get(f"/api/portfolios/{portfolio_id}").json()["name"] == "p"


@pytest.mark.parametrize(
    ("holdings", "status"),
    [
        ([{"symbol": "Z", "allocation": 100}], 404),
        ([{"symbol": "A", "allocation": 50}], 422),
    ],
)
def test_portfolio_invalid_update_keeps_portfolio(
    client: Client, portfolio_id: int, holdings, status: int
):
    url = f"/api/portfolios/{portfolio_id}"
    before = client.get(url).json()
    response = client.put(url, {"name": "q", "holdings": holdings}, JSON)
    assert response.status_code == status
    assert client.get(url).json() == before


def test_portfolio_delete_keeps_stocks(client: Client, portfolio_id: int):
    assert client.delete(f"/api/portfolios/{portfolio_id}").status_code == 204
    assert client.get("/api/portfolios").json() == []
    assert client.delete("/api/stocks/A").status_code == 204


def test_rebalance_without_cash(client: Client, portfolio_id: int):
    response = client.post(f"/api/portfolios/{portfolio_id}/rebalance", {}, JSON)
    assert response.status_code == 200
    plan = response.json()
    assert Decimal(plan["total_value"]) == 8
    trades = [(t["symbol"], t["action"], t["quantity"]) for t in plan["trades"]]
    assert trades == [("B", "SELL", 1), ("A", "BUY", 1)]
    assert Decimal(plan["cash_leftover"]) == Decimal("1.5")


def test_rebalance_conflict_message(client: Client, portfolio_id: int):
    url = f"/api/portfolios/{portfolio_id}/rebalance"
    client.post(url, {}, JSON)
    response = client.post(url, {}, JSON)
    assert response.json() == {"detail": "Portfolio has a pending rebalance plan"}


def test_rebalance_rejected_does_not_store_plan(client: Client, portfolio_id: int):
    url = f"/api/portfolios/{portfolio_id}"
    response = client.post(f"{url}/rebalance", {"cash": "-100"}, JSON)
    assert "cash must not be greater" in response.json()["detail"]
    assert client.get(url).json()["pending_plan"] is None


def test_execute_trades_without_plan(client: Client, portfolio_id: int):
    response = client.post(f"/api/portfolios/{portfolio_id}/execute-trades")
    assert response.status_code == 409
    assert response.json() == {"detail": "Portfolio has no pending rebalance plan"}


def test_execute_trades_uses_planned_price(client: Client, portfolio_id: int):
    url = f"/api/portfolios/{portfolio_id}"
    client.post(f"{url}/rebalance", {"cash": "5"}, JSON)
    client.put("/api/stocks/A", {"last_price": "100"}, JSON)

    body = client.post(f"{url}/execute-trades").json()
    assert _quantities(body) == {"A": 7, "B": 2}
    assert Decimal(body["cash_leftover"]) == 1
