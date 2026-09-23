import pytest

from data.resources import CUENTA_PRINCIPAL
from helpers.flow import activate_flow
from helpers.request_flow import approve, create_request
from schemas.validator import validate


@pytest.mark.request
def test_flujo_dos_niveles_aplica_cambios_al_aprobar_l2(
    admin_api,
    requester_api,
    approver_l1_api,
    approver_l2_api,
):
    """Con un flujo de 2 niveles activo, aprobar L1 no toca el recurso y aprobar L2 aplica el
    cambio por merge (conserva las demás claves); el log registra pending -> approved_l1 -> approved.
    """

    # Origen: semilla S-16 (migrado de test_environment.py)

    # Precondición: flujo activo de 2 niveles con sus aprobadores por defecto.
    activate_flow(admin_api, levels=2)

    # Acción: el solicitante pide cambiar el saldo de la Cuenta Principal.
    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )

    validate(created, "request")
    assert created["status"] == "pending"
    assert created["before"] == CUENTA_PRINCIPAL["values"]

    # L1 aprueba: la solicitud avanza pero el recurso todavía no cambia.
    l1 = approve(approver_l1_api, created["id"])
    assert l1["status"] == "approved_l1"

    resource_after_l1 = requester_api.get(f"/resources/{CUENTA_PRINCIPAL['id']}")
    assert resource_after_l1.status_code == 200, resource_after_l1.text
    validate(resource_after_l1.json(), "resource")
    assert resource_after_l1.json()["values"] == CUENTA_PRINCIPAL["values"]

    # L2 aprueba: el cambio se aplica por merge, conservando moneda y estado.
    l2 = approve(approver_l2_api, created["id"])
    assert l2["status"] == "approved"

    resource_after_l2 = requester_api.get(f"/resources/{CUENTA_PRINCIPAL['id']}")
    assert resource_after_l2.status_code == 200, resource_after_l2.text
    validate(resource_after_l2.json(), "resource")
    assert resource_after_l2.json()["values"] == {
        **CUENTA_PRINCIPAL["values"],
        "saldo": 999,
    }

    # Evidencia de negocio: el log registra la secuencia completa.
    log_resp = requester_api.get(f"/requests/{created['id']}/log")
    assert log_resp.status_code == 200, log_resp.text
    log = log_resp.json()
    for entry in log:
        validate(entry, "request_log_entry")

    assert [entry["to_status"] for entry in log] == ["pending", "approved_l1", "approved"]
