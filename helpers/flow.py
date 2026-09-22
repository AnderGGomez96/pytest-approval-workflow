from client.api_client import ApiClient
from data.payloads import flow_config
from data.payloads import approvers_config


def activate_flow (admin_api: ApiClient,levels: int = 2 ) -> dict:
    resp=admin_api.put("/flow/config", json= flow_config(levels, active=True))
    assert resp.status_code == 200, resp.text
    return resp.json()

def deactivate_flow (admin_api:ApiClient)->dict:
    resp=admin_api.put("/flow/config", json=flow_config(levels=2, active=False))
    assert resp.status_code == 200, resp.text
    return resp.json()

def get_flow_config(admin_api: ApiClient)->dict:
    resp=admin_api.get("/flow/config")
    assert resp.status_code == 200, resp.text
    return resp.json()

def set_approvers(admin_api: ApiClient, approvers: dict)->dict:
    resp=admin_api.put("/flow/approvers", json=approvers_config(approvers))
    assert resp.status_code == 200, resp.text
    return resp.json()

def get_flow_approvers(admin_api: ApiClient)->dict:
    resp=admin_api.get("/flow/approvers")
    assert resp.status_code == 200, resp.text
    return resp.json()

