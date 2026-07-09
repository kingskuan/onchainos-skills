from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

BASE = {"ingredients": ["egg", "tomato", "rice", "garlic", "pasta"]}


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_manifest():
    data = client.get("/a2a/manifest").json()
    assert data["service_name"] == "fridge-recipe-asp"
    assert "input_schema" in data


def test_cook_basic():
    resp = client.post("/cook", json=BASE)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["recipes"], list)
    assert len(data["recipes"]) >= 1
    assert "🍳" in data["markdown"]
    assert data["ingredients_provided"] == BASE["ingredients"]


def test_cook_returns_steps():
    resp = client.post("/cook", json={**BASE, "max_time_minutes": 60})
    data = resp.json()
    if data["recipes"]:
        assert len(data["recipes"][0]["steps"]) >= 1


def test_dietary_filter():
    resp = client.post("/cook", json={**BASE, "dietary": ["vegetarian"]})
    data = resp.json()
    for r in data["recipes"]:
        assert r["name"] not in ["Tuna Salad"]   # tuna is not vegetarian


def test_shopping_list():
    resp = client.post("/cook", json={"ingredients": ["egg"]})
    data = resp.json()
    assert isinstance(data["shopping_list"], list)


def test_a2a_invoke():
    resp = client.post("/a2a/invoke", json=BASE)
    assert resp.status_code == 200
    assert "markdown" in resp.json()
