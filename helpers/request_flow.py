from client.api_client import ApiClient
from data.payloads import conciliar

def create_request (
        requester_api:ApiClient,
        resource_id:int = 1,
        changes: dict | None = None,
        comment: str = "ajuste de prueba",
) -> dict:
    resp = requester_api.post(
        f"/resources/{resource_id}/conciliar",
        json=conciliar(changes or {"saldo":999}, comment),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def approve(approver_api:ApiClient, request_id: int) -> dict:
    resp = approver_api.post(f"/requests/{request_id}/approve")
    assert resp.status_code == 200, resp.text
    return resp.json()

def reject(approver_api:ApiClient, request_id:int) -> dict:
    resp=approver_api.post(f"/requests/{request_id}/reject")
    assert resp.status_code == 200, resp.text
    return resp.json()

def cancel (requester_api:ApiClient, request_id:int)->dict:
    resp= requester_api.post (f"/requests/{request_id}/cancel")
    assert resp.status_code == 200, resp.text
    return resp.json()

def get_request_detail (api:ApiClient, request_id:int)->dict:
    resp= api.get (f"/requests/{request_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()

def get_request_log (api:ApiClient, request_id:int)->list[dict]:
    resp= api.get (f"/requests/{request_id}/log")
    assert resp.status_code == 200, resp.text
    return resp.json()