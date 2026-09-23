from client.api_client import ApiClient


def received_items(api: ApiClient) -> list[dict]:
    resp = api.get("/inbox/received")
    assert resp.status_code == 200, resp.text
    return resp.json()


def sent_items(api: ApiClient) -> list[dict]:
    resp = api.get("/inbox/sent")
    assert resp.status_code == 200, resp.text
    return resp.json()


def received_ids(api: ApiClient) -> list[int]:
    return [item["id"] for item in received_items(api)]


def sent_ids(api: ApiClient) -> list[int]:
    return [item["id"] for item in sent_items(api)]
