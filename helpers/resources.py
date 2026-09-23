from client.api_client import ApiClient


def list_resources(api: ApiClient) -> list[dict]:
    resp = api.get("/resources")
    assert resp.status_code == 200, resp.text
    return resp.json()


def get_resource(api: ApiClient, resource_id: int) -> dict:
    resp = api.get(f"/resources/{resource_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()
