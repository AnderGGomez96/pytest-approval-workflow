import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import USER_IDS
from helpers.flow import (
    activate_flow,
    get_flow_approvers,
    get_flow_config,
    get_flow_overrides,
    set_approvers_override,
)
from helpers.inbox import received_ids, sent_ids
from helpers.request_flow import approve, cancel, create_request, get_request_detail
from helpers.resources import list_resources
from schemas.validator import validate

pytestmark = pytest.mark.default

# Estado inicial tras el reset (handoff §3.1): 5 contadores de escritura en 0.
_SEED_COUNTS = {
    "users": 10,
    "workspaces": 1,
    "flow_config": 1,
    "ws_approvers": 0,
    "overrides": 0,
    "resources": 3,
    "requests": 0,
    "request_assignments": 0,
    "request_transitions": 0,
}


def _reset(anonymous_api) -> dict:
    """POST /test/reset sin token; devuelve el body con `status` y `counts`."""
    resp = anonymous_api.post("/test/reset")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _snapshot(admin_api, requester_api, anonymous_api) -> dict:
    """Resetea y captura todo el estado observable por API para comparar corridas."""
    data = _reset(anonymous_api)
    return {
        "status": data["status"],
        "counts": data["counts"],
        "config": get_flow_config(admin_api),
        "approvers": get_flow_approvers(admin_api),
        "override_9": get_flow_overrides(admin_api, USER_IDS["requester_override"]),
        "resources": list_resources(admin_api),
        "received": received_ids(requester_api),
        "sent": sent_ids(requester_api),
    }


@pytest.mark.regresion
def test_reset_restaura_estado_sembrado_tras_mutaciones(
    admin_api, requester_api, approver_l1_api, approver_l2_api, anonymous_api
):
    """S-27/AC-9.1: tras mutar config, override, recurso y solicitudes, el reset vuelve al seed."""

    # Mutación 1: conciliar con el flujo inactivo aplica directo y altera el recurso.
    conciliado = requester_api.post(
        f"/resources/{CUENTA_PRINCIPAL['id']}/conciliar",
        json={"changes": {"saldo": 777}},
    )
    assert conciliado.status_code == 200, conciliado.text
    assert conciliado.json()["values"]["saldo"] == 777

    # Mutación 2: flujo de 2 niveles activo y un override del usuario 9.
    activate_flow(admin_api, levels=2)
    set_approvers_override(admin_api, USER_IDS["requester_override"], {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    })

    # Mutación 3: una solicitud resuelta, una cancelada y una en vuelo (ids de la respuesta).
    resuelta = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 111}
    )
    approve(approver_l1_api, resuelta["id"])
    approve(approver_l2_api, resuelta["id"])

    cancelada = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 222}
    )
    cancel(requester_api, cancelada["id"])

    en_vuelo = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 333}
    )
    ids_previos = {resuelta["id"], cancelada["id"], en_vuelo["id"]}

    # Acción bajo prueba: reset sin token.
    data = _reset(anonymous_api)

    assert data["status"] == "reset"
    assert data["counts"] == _SEED_COUNTS

    # Estado visible restaurado: config, approvers, override, recursos y bandejas.
    config = get_flow_config(admin_api)
    validate(config, "flow_config")
    assert config == {"levels": 2, "active": False}

    approvers = get_flow_approvers(admin_api)
    validate(approvers, "flow_approvers")
    assert approvers == {"level_1": [], "level_2": []}

    override = get_flow_overrides(admin_api, USER_IDS["requester_override"])
    validate(override, "flow_overrides")
    assert override == {
        "user_id": USER_IDS["requester_override"],
        "level_1": [],
        "level_2": [],
    }

    recursos = list_resources(admin_api)
    assert len(recursos) == 3
    principal = next(r for r in recursos if r["id"] == CUENTA_PRINCIPAL["id"])
    validate(principal, "resource")
    assert principal["values"] == CUENTA_PRINCIPAL["values"]
    assert principal["values"]["saldo"] == 1000

    assert sent_ids(requester_api) == []
    assert received_ids(approver_l1_api) == []
    assert received_ids(approver_l2_api) == []
    for previo in ids_previos:
        assert previo not in sent_ids(requester_api)
        assert previo not in received_ids(approver_l1_api)

    # El id previo ya no existe: el helper lo evidencia levantando AssertionError por el 404.
    with pytest.raises(AssertionError):
        get_request_detail(requester_api, en_vuelo["id"])

    # Confirmación del código real con el cliente directo (acción negativa, como en C-001).
    resp = requester_api.get(f"/requests/{en_vuelo['id']}")
    assert resp.status_code == 404, resp.text
    validate(resp.json(), "error")


def test_reset_dos_corridas_mismo_estado(admin_api, requester_api, anonymous_api):
    """S-27/AC-9.2: dos resets con una mutación en medio dejan el mismo estado observable."""

    primero = _snapshot(admin_api, requester_api, anonymous_api)

    # Mutación intermedia: activa el flujo, define un override y crea/cancela una solicitud.
    activate_flow(admin_api, levels=2)
    set_approvers_override(admin_api, USER_IDS["requester_override"], {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    })
    cancelada = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 444}
    )
    cancel(requester_api, cancelada["id"])

    # La mutación es real: sin el segundo reset el estado no coincidiría con el seed.
    assert get_flow_config(admin_api) == {"levels": 2, "active": True}
    assert get_flow_approvers(admin_api)["level_1"] == [USER_IDS["approver_l1"]]
    assert sent_ids(requester_api) != []

    segundo = _snapshot(admin_api, requester_api, anonymous_api)

    assert segundo == primero
    assert segundo["counts"] == _SEED_COUNTS


def test_reset_sin_token_y_operativo_despues(admin_api, requester_api, anonymous_api):
    """S-27/AC-9.3-9.4: el reset no exige token y deja la precondición C-002 operativa."""

    data = _reset(anonymous_api)
    assert data["status"] == "reset"
    assert data["counts"] == _SEED_COUNTS

    # Tras el reset, la precondición C-002 y una creación vuelven a funcionar.
    activate_flow(admin_api, levels=2)
    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    assert isinstance(created["id"], int) and created["id"] > 0
