import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow
from helpers.request_flow import (
    approve,
    cancel,
    create_request,
    get_request_detail,
    get_request_log,
    reject,
)
from helpers.resources import get_resource
from schemas.validator import validate

pytestmark = pytest.mark.request

# Flujo de 2 niveles con L1 [4, 5] y L2 [6].
APROBADORES_2_NIVELES = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [USER_IDS["approver_l2"]],
}


def test_detalle_evoluciona_pending_l1_aprobado(
    admin_api, requester_api, api, approver_l1_api, approver_l2_api
):
    """El detalle conserva applied == before en pending y approved_l1 y pasa a
    merge(before, proposed) en approved; L1 lee en pending y L2 en approved_l1/approved (AC-8.1, AC-8.5)."""

    activate_flow(admin_api, levels=2, approvers=APROBADORES_2_NIVELES)
    approver_l1_dos_api = api(TOKENS["approver_l1_dos"])
    merge = {**CUENTA_PRINCIPAL["values"], "saldo": 999}

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # pending: applied == before; el solicitante siempre lo ve y L1 (4 y 5) tiene visibilidad.
    detail_pending = get_request_detail(requester_api, request_id)
    validate(detail_pending, "request_detail")
    assert detail_pending["before"] == CUENTA_PRINCIPAL["values"]
    assert detail_pending["proposed"] == {"saldo": 999}
    assert detail_pending["applied"] == detail_pending["before"]
    for l1 in (approver_l1_api, approver_l1_dos_api):
        detail_l1_view = get_request_detail(l1, request_id)
        validate(detail_l1_view, "request_detail")
        assert detail_l1_view["applied"] == detail_l1_view["before"]

    # L1 aprueba: la solicitud avanza pero el detalle sigue con applied == before.
    resolved_l1 = approve(approver_l1_api, request_id)
    validate(resolved_l1, "request")
    assert resolved_l1["status"] == "approved_l1"

    detail_approved_l1 = get_request_detail(requester_api, request_id)
    validate(detail_approved_l1, "request_detail")
    assert detail_approved_l1["applied"] == detail_approved_l1["before"]

    # AC-8.5: en approved_l1 el detalle es visible para L2 (6).
    detail_l2_view = get_request_detail(approver_l2_api, request_id)
    validate(detail_l2_view, "request_detail")
    assert detail_l2_view["applied"] == detail_l2_view["before"]

    # L2 aprueba: el detalle refleja el merge(before, proposed), sin reemplazar el resto.
    resolved_l2 = approve(approver_l2_api, request_id)
    validate(resolved_l2, "request")
    assert resolved_l2["status"] == "approved"

    detail_approved = get_request_detail(requester_api, request_id)
    validate(detail_approved, "request_detail")
    assert detail_approved["before"] == CUENTA_PRINCIPAL["values"]
    assert detail_approved["proposed"] == {"saldo": 999}
    assert detail_approved["applied"] == merge
    assert detail_approved["applied"] != detail_approved["before"]

    # AC-8.5: en approved (último nivel) L2 sigue leyendo el detalle.
    detail_l2_approved = get_request_detail(approver_l2_api, request_id)
    validate(detail_l2_approved, "request_detail")
    assert detail_l2_approved["applied"] == merge


def test_detalle_rechazada_y_cancelada_no_aplica(
    admin_api, requester_api, api, approver_l1_api
):
    """En rejected y cancelled el detalle mantiene applied == before con proposed intacto;
    4 y 5 leen el detalle en rejected (AC-8.1, AC-8.5)."""

    activate_flow(admin_api, levels=2, approvers=APROBADORES_2_NIVELES)
    approver_l1_dos_api = api(TOKENS["approver_l1_dos"])
    merge = {**CUENTA_PRINCIPAL["values"], "saldo": 999}

    # Rama rejected: rechazo en L1, sin aplicar.
    rejected = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(rejected, "request")
    assert rejected["status"] == "pending"
    rejected_id = rejected["id"]
    assert isinstance(rejected_id, int) and rejected_id > 0

    resolved = reject(approver_l1_api, rejected_id)
    validate(resolved, "request")
    assert resolved["status"] == "rejected"

    detail_rejected = get_request_detail(requester_api, rejected_id)
    validate(detail_rejected, "request_detail")
    assert detail_rejected["before"] == CUENTA_PRINCIPAL["values"]
    assert detail_rejected["proposed"] == {"saldo": 999}
    assert detail_rejected["applied"] == detail_rejected["before"]
    assert detail_rejected["applied"] != merge

    # AC-8.5: 4 y 5 leen detalle y log en rejected.
    for l1 in (approver_l1_api, approver_l1_dos_api):
        detail_l1_view = get_request_detail(l1, rejected_id)
        validate(detail_l1_view, "request_detail")
        assert detail_l1_view["applied"] == detail_l1_view["before"]
        log_l1_view = get_request_log(l1, rejected_id)
        for entry in log_l1_view:
            validate(entry, "request_log_entry")
        assert [entry["to_status"] for entry in log_l1_view] == ["pending", "rejected"]

    # El recurso conserva los valores seed tras el rechazo.
    resource_rejected = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource_rejected, "resource")
    assert resource_rejected["values"] == CUENTA_PRINCIPAL["values"]

    # Rama cancelled: el solicitante cancela en pending, sin aplicar.
    cancelled = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(cancelled, "request")
    assert cancelled["status"] == "pending"
    cancelled_id = cancelled["id"]
    assert isinstance(cancelled_id, int) and cancelled_id > 0

    resolved_cancel = cancel(requester_api, cancelled_id)
    validate(resolved_cancel, "request")
    assert resolved_cancel["status"] == "cancelled"

    detail_cancelled = get_request_detail(requester_api, cancelled_id)
    validate(detail_cancelled, "request_detail")
    assert detail_cancelled["before"] == CUENTA_PRINCIPAL["values"]
    assert detail_cancelled["proposed"] == {"saldo": 999}
    assert detail_cancelled["applied"] == detail_cancelled["before"]
    assert detail_cancelled["applied"] != merge

    # El recurso conserva los valores seed tras la cancelación.
    resource_cancelled = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource_cancelled, "resource")
    assert resource_cancelled["values"] == CUENTA_PRINCIPAL["values"]


def test_log_registra_creacion_y_transiciones(
    admin_api, requester_api, api, approver_l1_api, approver_l2_api
):
    """El log registra la creación con el actor del solicitante y cada transición con el actor
    real; created_at no decreciente y un 409 no añade entradas (AC-8.2, N-14)."""

    activate_flow(admin_api, levels=2, approvers=APROBADORES_2_NIVELES)
    requester_2_api = api(TOKENS["requester_2"])

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Recién creada: exactamente 1 entrada create, con el actor del solicitante.
    log = get_request_log(requester_api, request_id)
    assert len(log) == 1
    for entry in log:
        validate(entry, "request_log_entry")
    assert log[0]["action"] == "create"
    assert log[0]["from_status"] is None
    assert log[0]["to_status"] == "pending"
    assert isinstance(log[0]["actor_name"], str) and log[0]["actor_name"]
    solicitante_actor = log[0]["actor_name"]

    # Identidad del actor de creación: estable para el mismo solicitante, distinta para otro.
    otro_mismo = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    assert get_request_log(requester_api, otro_mismo["id"])[0]["actor_name"] == solicitante_actor
    otro_distinto = create_request(
        requester_2_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    assert (
        get_request_log(requester_2_api, otro_distinto["id"])[0]["actor_name"]
        != solicitante_actor
    )

    # L1 aprueba: una entrada más con el actor real (distinto del solicitante).
    approve(approver_l1_api, request_id)
    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "approved_l1"]
    assert log[1]["action"] == "approve"
    assert log[1]["from_status"] == "pending"
    assert isinstance(log[1]["actor_name"], str) and log[1]["actor_name"]
    assert log[1]["actor_name"] != solicitante_actor

    # L2 aprueba: secuencia completa con los actores reales.
    approve(approver_l2_api, request_id)
    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "approved_l1", "approved"]
    assert log[2]["action"] == "approve"
    assert log[2]["from_status"] == "approved_l1"
    assert isinstance(log[2]["actor_name"], str) and log[2]["actor_name"]
    assert log[2]["actor_name"] != solicitante_actor
    assert log[2]["actor_name"] != log[1]["actor_name"]
    assert all(
        log[index]["created_at"] <= log[index + 1]["created_at"]
        for index in range(len(log) - 1)
    )

    # Un segundo approve sobre el estado final da 409 y no añade entradas al log.
    resp = approver_l2_api.post(f"/requests/{request_id}/approve")
    assert resp.status_code == 409, resp.text
    validate(resp.json(), "error")

    log_after = get_request_log(requester_api, request_id)
    assert [entry["to_status"] for entry in log_after] == [
        "pending",
        "approved_l1",
        "approved",
    ]
