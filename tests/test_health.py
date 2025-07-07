def test_health_endpoint(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert isinstance(response.json, dict)
    assert response.json.get('status') == 'ok'