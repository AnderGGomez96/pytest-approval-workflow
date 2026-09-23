import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow
from helpers.inbox import received_ids
from helpers.request_flow import (
    approve,
    create_request,
    get_request_detail,
    get_request_log,
)
from helpers.resources import get_resource
from schemas.validator import validate


@pytest.mark.request
@pytest.mark.regresion
def test_flujo_dos_niveles_aplica_cambios_al_aprobar_l2(
    admin_api,
    requester_api,
    api,
    approver_l1_api,
    approver_l2_api,
):
    """Con un flujo de 2 niveles activo, aprobar L1 no toca el recurso y aprobar L2 aplica el
    cambio por merge (conserva las demás claves); el log registra pending -> approved_l1 -> approved.
    Mientras está pending la ven los aprobadores de L1 (4 y 5) y no L2 (6); al aprobar L1 la
    visibilidad pasa a 6 y el detalle conserva applied == before hasta que L2 aprueba.
    """

    # Origen: semilla S-16 (migrado de los tests de ambiente del arranque, retirados en C-001)

    # Precondición: flujo activo de 2 niveles con L1 [4, 5] y L2 [6].
    activate_flow(
        admin_api,
        levels=2,
        approvers={
            "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
            "level_2": [USER_IDS["approver_l2"]],
        },
    )
    approver_l1_dos_api = api(TOKENS["approver_l1_dos"])

    # Acción: el solicitante pide cambiar el saldo de la Cuenta Principal.
    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )

    validate(created, "request")
    assert created["status"] == "pending"
    assert created["before"] == CUENTA_PRINCIPAL["values"]

    # Visibilidad inicial: en pending la ven los aprobadores de L1 (4 y 5), no L2 (6).
    assert created["id"] in received_ids(approver_l1_api)
    assert created["id"] in received_ids(approver_l1_dos_api)
    assert created["id"] not in received_ids(approver_l2_api)

    # L1 aprueba: la solicitud avanza pero el recurso todavía no cambia.
    l1 = approve(approver_l1_api, created["id"])
    assert l1["status"] == "approved_l1"

    # Al aprobar L1 la visibilidad pasa a L2: 6 la ve y 4/5 dejan de verla.
    assert created["id"] in received_ids(approver_l2_api)
    assert created["id"] not in received_ids(approver_l1_api)
    assert created["id"] not in received_ids(approver_l1_dos_api)

    # El detalle aún no refleja el cambio propuesto: applied sigue igual a before.
    detail_after_l1 = get_request_detail(requester_api, created["id"])
    validate(detail_after_l1, "request_detail")
    assert detail_after_l1["applied"] == detail_after_l1["before"]

    resource_after_l1 = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource_after_l1, "resource")
    assert resource_after_l1["values"] == CUENTA_PRINCIPAL["values"]

    # L2 aprueba: el cambio se aplica por merge, conservando moneda y estado.
    l2 = approve(approver_l2_api, created["id"])
    assert l2["status"] == "approved"

    resource_after_l2 = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource_after_l2, "resource")
    assert resource_after_l2["values"] == {
        **CUENTA_PRINCIPAL["values"],
        "saldo": 999,
    }

    # Evidencia de negocio: el log registra la secuencia completa.
    log = get_request_log(requester_api, created["id"])
    for entry in log:
        validate(entry, "request_log_entry")

    assert [entry["to_status"] for entry in log] == ["pending", "approved_l1", "approved"]
