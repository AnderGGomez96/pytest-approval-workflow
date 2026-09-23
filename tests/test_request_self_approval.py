import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow, set_approvers_override
from helpers.inbox import received_ids, sent_items
from helpers.request_flow import (
    approve,
    cancel,
    create_request,
    get_request_detail,
    get_request_log,
)
from helpers.resources import get_resource
from schemas.validator import validate

pytestmark = pytest.mark.request

# Precondición C-002: el solicitante 2 es el único aprobador L1 -> conjunto efectivo vacío.
SOLO_SOLICITANTE_L1 = {
    "level_1": [USER_IDS["requester"]],
    "level_2": [],
}

# Precondición C-002 de 2 niveles: L1 = {4, 5}, L2 = {6}.
WORKSPACE_2_LEVELS = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [USER_IDS["approver_l2"]],
}


def _assert_business_detail(detail) -> None:
    """Un error de negocio trae `detail` como lista no vacía de strings."""
    assert isinstance(detail, list) and detail, detail
    assert all(isinstance(item, str) for item in detail), detail


def test_solicitante_unico_aprobador_queda_estacionada(admin_api, requester_api, api):
    """Con `[2]/[]` la solicitud de 2 queda estacionada: ningún aprobador la recibe, sigue en las
    enviadas de 2 y nadie puede resolverla (AC-5.2, S-20)."""

    activate_flow(admin_api, levels=1, approvers=SOLO_SOLICITANTE_L1)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Conjunto efectivo vacío: ningún aprobador del seed la recibe.
    for token in (TOKENS["approver_l1"], TOKENS["approver_l1_dos"], TOKENS["approver_l2"]):
        assert request_id not in received_ids(api(token)), token

    # El solicitante la conserva en enviadas con su estado real.
    sent = sent_items(requester_api)
    assert request_id in [item["id"] for item in sent]
    sent_item = next(item for item in sent if item["id"] == request_id)
    validate(sent_item, "inbox_item")
    assert sent_item["status"] == "pending"

    # El recurso nunca se aplica: applied == before.
    detail = get_request_detail(requester_api, request_id)
    validate(detail, "request_detail")
    assert detail["before"] == CUENTA_PRINCIPAL["values"]
    assert detail["applied"] == detail["before"]

    log_before = get_request_log(requester_api, request_id)
    for entry in log_before:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log_before] == ["pending"]

    # Sin visibilidad 4/5/6 reciben 404; el solicitante sobre lo suyo -> 403.
    for token in (TOKENS["approver_l1"], TOKENS["approver_l1_dos"], TOKENS["approver_l2"]):
        resp = api(token).post(f"/requests/{request_id}/approve")
        assert resp.status_code == 404, resp.text
        validate(resp.json(), "error")
        _assert_business_detail(resp.json()["detail"])

    propio = requester_api.post(f"/requests/{request_id}/approve")
    assert propio.status_code == 403, propio.text
    validate(propio.json(), "error")
    assert isinstance(propio.json()["detail"], str) and propio.json()["detail"]

    # Sin transición: sigue pending y el log no registra ninguna aprobación.
    log_after = get_request_log(requester_api, request_id)
    assert len(log_after) == len(log_before)
    assert log_after[-1]["to_status"] == "pending"
    assert all(entry["to_status"] != "approved" for entry in log_after)


def test_solicitante_estacionada_puede_cancelar(admin_api, requester_api):
    """El solicitante cancela su solicitud estacionada: `200 cancelled`, recurso intacto y log
    `pending -> cancelled` con el actor del solicitante (AC-5.3, S-20)."""

    activate_flow(admin_api, levels=1, approvers=SOLO_SOLICITANTE_L1)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Acción bajo prueba: 2 cancela su solicitud estacionada.
    cancelled = cancel(requester_api, request_id)

    validate(cancelled, "request")
    assert cancelled["id"] == request_id
    assert cancelled["status"] == "cancelled"

    # Evidencia de negocio: el recurso conserva exactamente los valores seed.
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    # El log registra la cancelación con el actor real (el mismo solicitante que creó).
    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "cancelled"]
    assert log[1]["action"] == "cancel"
    assert log[1]["from_status"] == "pending"
    assert isinstance(log[1]["actor_name"], str) and log[1]["actor_name"]
    assert log[1]["actor_name"] == log[0]["actor_name"]


def test_exclusion_del_solicitante_con_override(admin_api, requester_api, api):
    """Con WS `[4,5]/[6]` y override `2 -> [2,4]/[]`, el solicitante queda excluido: solo 4 recibe
    L1, 4 aprueba y L2 usa el WS (6) (AC-5.4)."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)
    set_approvers_override(
        admin_api,
        USER_IDS["requester"],
        {
            "level_1": [USER_IDS["requester"], USER_IDS["approver_l1"]],
            "level_2": [],
        },
    )

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # El override incluye a 2, pero el solicitante se excluye del conjunto efectivo: solo 4.
    assert request_id in received_ids(api(TOKENS["approver_l1"]))
    assert request_id not in received_ids(api(TOKENS["approver_l1_dos"]))
    assert request_id not in received_ids(requester_api)

    # 4 resuelve L1; la asignación L2 sale del WS (6), no del override (que no aporta L2).
    l1 = approve(api(TOKENS["approver_l1"]), request_id)
    validate(l1, "request")
    assert l1["status"] == "approved_l1"

    assert request_id in received_ids(api(TOKENS["approver_l2"]))
    assert request_id not in received_ids(api(TOKENS["override_l2"]))

    l2 = approve(api(TOKENS["approver_l2"]), request_id)
    validate(l2, "request")
    assert l2["status"] == "approved"

    # El recurso se aplica por merge al cerrar L2.
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}
