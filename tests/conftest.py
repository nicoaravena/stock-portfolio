import pytest
from django.test import Client

JSON = "application/json"


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def stocks(client: Client):
    client.post("/api/stocks", {"symbol": "A", "last_price": "1.0"}, JSON)
    client.post("/api/stocks", {"symbol": "B", "last_price": "2.5"}, JSON)


@pytest.fixture
def portfolio_id(client: Client, stocks) -> int:
    response = client.post(
        "/api/portfolios",
        {
            "name": "p",
            "holdings": [
                {"symbol": "A", "quantity": 3, "allocation": 60},
                {"symbol": "B", "quantity": 2, "allocation": 40},
            ],
        },
        JSON,
    )
    assert response.status_code == 201
    return response.json()["id"]
