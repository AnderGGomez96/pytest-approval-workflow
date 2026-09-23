import os
import time
import pytest
import requests

from client.api_client import ApiClient
from data.tokens import TOKENS

@pytest.fixture(scope="session")
def api_base_url() -> str:
    return os.environ.get("APPROVAL_BASE_URL")

@pytest.fixture(scope="session",autouse=True)
def wait_until_reade(api_base_url:str)->None:
    """Espera /health antes de la suite: sin skip: si no responde, fall."""
    deadline = time.monotonic()+30
    while time.monotonic()<deadline:
        try:
            if requests.get(f"{api_base_url}/health", timeout=2.0).status_code==200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.2)
    pytest.fail(f"La API no respondio /health en 30s: {api_base_url}")

@pytest.fixture(autouse=True)
def reset_stat(api_base_url:str)->None:
    """Estado sembrado conocido antes de cada test; sin dependencia de orden"""
    resp = requests.post(f"{api_base_url}/test/reset",timeout=10.0)
    assert resp.status_code == 200, resp.text

@pytest.fixture
def api(api_base_url: str):
    """Fabrica de clientes por token, los cierra al final del test."""
    clients: list[ApiClient] = []

    def _make (token: str | None = None)->ApiClient:
        client = ApiClient(api_base_url, token=token)
        clients.append(client)
        return client

    yield _make
    for client in clients: 
        client.close()


@pytest.fixture
def admin_api(api):
    return api(TOKENS["admin"])

@pytest.fixture
def requester_api(api):
    return api(TOKENS["requester"])


@pytest.fixture
def approver_l1_api(api):
    return api(TOKENS["approver_l1"])


@pytest.fixture
def approver_l2_api(api):
    return api(TOKENS["approver_l2"])


@pytest.fixture
def anonymous_api(api):
    return api(None)