import pytest
from schemas.validator import validate
from helpers.flow import get_flow_config, set_approvers
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow

@pytest.mark.parametrize(
        ("token", "expected_status_code", "detail" ),
        [
            (TOKENS["inactive"], 401, "Credenciales inválidas" ),
            (TOKENS["requester"], 403, "Requiere administrador" ),
            (TOKENS["approver_l1"], 403, "Requiere administrador" ),
            (TOKENS["approver_l2"], 403, "Requiere administrador" ),
            (TOKENS["admin"], 200,  ""),
        ]
)
def test_solo_admin_activa_flujo(api, admin_api, token, expected_status_code, detail):

    # Precondición: definir aprobadores por nivel
    set_approvers(admin_api, approvers={
            "level_1":[USER_IDS["approver_l1"]],
            "level_2":[USER_IDS["approver_l2"]]
        })


    resp = api(token).put("/flow/config", json={"active": True, "levels": 2})
    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()

    if expected_status_code == 200:
        validate(data, "flow_config")
        assert data["active"] == True
        assert data["levels"] == 2

        #Evidencia de negocio: el flujo se encuentra activo.
        flow_config = get_flow_config(api(token))
        assert flow_config["active"] == True

    if expected_status_code > 400:
        validate(data, "error")
        assert data["detail"] == detail

        # Evidencia de negocio: El flujo no se encuentra activo.
        flow_config = get_flow_config(api(TOKENS["admin"]))
        assert  flow_config["active"] == False


@pytest.mark.parametrize(
        ("token", "expected_status_code", "detail" ),
        [
            (TOKENS["inactive"], 401, "Credenciales inválidas" ),
            (TOKENS["requester"], 403, "Requiere administrador" ),
            (TOKENS["approver_l1"], 403, "Requiere administrador" ),
            (TOKENS["approver_l2"], 403, "Requiere administrador" ),
            (TOKENS["admin"], 200,  ""),
        ]
)
def test_solo_admin_desactiva_flujo(api, admin_api, token, expected_status_code, detail):

    # Precondición: flujo activo
    activate_flow(admin_api, levels=2)

    #Accion: desactivar flujo
    resp = api(token).put("/flow/config", json={"active": False, "levels": 2})
    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()

    if expected_status_code == 200:
        validate(data, "flow_config")
        assert data["active"] == False

        flow_config = get_flow_config(api(token))
        assert flow_config["active"] == False

    if expected_status_code > 400:
        validate(data, "error")
        assert data["detail"] == detail

        # Evidencia de negocio: El flujo no se encuentra activo.
        flow_config = get_flow_config(api(TOKENS["admin"]))
        assert  flow_config["active"] == True