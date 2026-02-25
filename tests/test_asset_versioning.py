from fastapi.testclient import TestClient

from app.main import app


def test_homepage_includes_cache_busted_asset_urls():
    client = TestClient(app)
    response = client.get('/')

    assert response.status_code == 200
    html = response.text
    token = app.state.asset_version

    assert f'/static/css/site.css?v={token}' in html
    assert f'/static/js/htmx.min.js?v={token}' in html
