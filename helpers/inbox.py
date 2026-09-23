from client.api_client import ApiClient


def received_ids(api: ApiClient) -> list[int]:
    resp = api.get("/inbox/received")
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()]


def sent_ids(api: ApiClient) -> list[int]:
    resp = api.get("/inbox/sent")
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()]
