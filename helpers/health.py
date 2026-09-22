from client.api_client import ApiClient

def check_health(admin_api: ApiClient) -> dict:
    resp = admin_api.get("/health")
    assert resp.status_code == 200, resp.text
    return resp.json()