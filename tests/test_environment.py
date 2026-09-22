import pytest
from data.resources import CUENTA_PRINCIPAL
from data.tokens import USER_IDS
from helpers.flow import activate_flow, set_approvers,get_flow_approvers
from helpers.request_flow import approve, create_request
from schemas.validator import validate


def test_flujo_dos_niveles_aplica_cambios_al_aprobar_l2(
    admin_api, 
    requester_api, 
    approver_l1_api,
    approver_l2_api
):

    # Precondición:flujo activo de 2 niveles
    activate_flow(admin_api, levels=2)

    #Accion: Crear solicitud de cambio.
    created = create_request(requester_api, resource_id=1, changes= {"saldo":999})

    validate(created, "request")

    assert created["status"] == "pending"
    assert created["before"] ==  CUENTA_PRINCIPAL["values"]

    #L1 aprueba

    l1 = approve(approver_l1_api, created["id"])
    assert l1["status"] == "approved_l1"
    assert requester_api.get("/resources/1").json()["values"] == CUENTA_PRINCIPAL["values"]

    #L2 apprueba
    l2 = approve(approver_l2_api, created["id"])
    assert l2["status"] == "approved"
    assert requester_api.get("/resources/1").json()["values"] == {
        **CUENTA_PRINCIPAL["values"],
        "saldo":434
    }

    # Evidencia de negocio: el log registra la secuencia completa.

    log = requester_api.get(f"/requests/{created['id']}/log").json()
    for entry in log:
        validate(entry, "request_log_entry")

    assert [entry["to_status"] for entry in log ] == ["pending","approved_l1","approved"]



def test_definir_aprobadores_por_nivel(admin_api, approver_l1_api, approver_l2_api):

    # Precondición:flujo activo de 2 niveles
    activate_flow(admin_api, levels=2)

    approver_l1_id = USER_IDS["approver_l1"]
    approver_l2_id = USER_IDS["approver_l2"]

    #Accion: Definir aprobadores por nivel.
    approvers= set_approvers(admin_api, approvers={
        "level_1":[approver_l1_id],
        "level_2":[approver_l2_id]
    })

    validate(approvers, "flow_approvers")

    assert approvers["level_1"] == [approver_l1_id]
    assert approvers["level_2"] == [approver_l2_id]

    # Evidencia de negocio: la API devuelve los aprobadores definidos.
    retrieved_approvers = get_flow_approvers(admin_api)
    validate(retrieved_approvers, "flow_approvers")

    assert retrieved_approvers["level_1"] == [approver_l1_id]
    assert retrieved_approvers["level_2"] == [approver_l2_id]
