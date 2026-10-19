"""
Tests for the base routes
"""


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "en" in response.json()["supported_languages"]


def test_languages(client):
    response = client.get("/v1/languages")
    assert response.status_code == 200
    assert set(response.json()["languages"]) == {"en", "yo", "ha", "ig"}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
