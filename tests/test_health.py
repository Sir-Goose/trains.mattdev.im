from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_expected_shape():
    client = TestClient(app)
    response = client.get('/api/health')

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'healthy'
    assert 'cache_ttl' in payload
    assert 'cache_backend' in payload
