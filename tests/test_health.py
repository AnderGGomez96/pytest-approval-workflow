import pytest
from helpers.health import check_health

def test_health_check(admin_api):
    """Verifica que la API responde /health y devuelve un JSON con status=ok"""
    data = check_health(admin_api)
    assert data.get("status") == "ok"