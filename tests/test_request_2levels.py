import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow, set_approvers, set_approvers_override
from helpers.inbox import received_ids
from helpers.request_flow import (
    approve,
    create_request,
    get_request_detail,
    get_request_log,
    reject,
)
from helpers.resources import get_resource
from schemas.validator import validate

pytestmark = pytest.mark.request

# Precondición C-002 de 2 niveles: L1 = {4, 5}, L2 = {6}.
WORKSPACE_2_LEVELS = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [USER_IDS["approver_l2"]],
}


def _assert_business_detail(detail) -> None:
    """Un error de negocio trae `detail` como lista no vacía de strings."""
    assert isinstance(detail, list) and detail, detail
    assert all(isinstance(item, str) for item in detail), detail


@pytest.mark.regresion
def test_dos_niveles_rechazo_l1_no_llega_a_l2(
    admin_api, requester_api, approver_l1_api, approver_l2_api
):
    """El rechazo en L1 deja la solicitud `rejected`, nunca escala a L2 y el recurso no cambia."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # En pending la ve L1; L2 todavía no.
    assert request_id in received_ids(approver_l1_api)
    assert request_id not in received_ids(approver_l2_api)

    rejected = reject(approver_l1_api, request_id)
    validate(rejected, "request")
    assert rejected["status"] == "rejected"
    assert rejected["id"] == request_id
    assert rejected["before"] == CUENTA_PRINCIPAL["values"]

    # L2 nunca la ve: rechazada en L1 no escala.
    assert request_id not in received_ids(approver_l2_api)

    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "rejected"]

    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]


def test_dos_niveles_rechazo_l2_no_aplica(
    admin_api, requester_api, approver_l1_api, approver_l2_api
):
    """Aprobar L1 y rechazar L2 deja la solicitud `rejected` sin aplicar el cambio propuesto."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    l1 = approve(approver_l1_api, request_id)
    validate(l1, "request")
    assert l1["status"] == "approved_l1"

    # Tras L1 el recurso aún no se toca: `applied == before`.
    detail_after_l1 = get_request_detail(requester_api, request_id)
    validate(detail_after_l1, "request_detail")
    assert detail_after_l1["applied"] == detail_after_l1["before"] == CUENTA_PRINCIPAL["values"]

    rejected = reject(approver_l2_api, request_id)
    validate(rejected, "request")
    assert rejected["status"] == "rejected"
    assert rejected["proposed"] == {"saldo": 999}

    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "approved_l1", "rejected"]

    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    detail_after_reject = get_request_detail(requester_api, request_id)
    validate(detail_after_reject, "request_detail")
    assert detail_after_reject["applied"] == detail_after_reject["before"] == CUENTA_PRINCIPAL["values"]


@pytest.mark.regresion
def test_dos_niveles_l2_sin_l1_404(admin_api, requester_api, approver_l2_api):
    """Resolver en L2 con la solicitud en `pending` (sin L1) es no-visible: `404` sin transición."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0
    log_before = get_request_log(requester_api, request_id)

    # Acción bajo prueba: L2 intenta aprobar en pending.
    resp = approver_l2_api.post(f"/requests/{request_id}/approve")

    assert resp.status_code == 404, resp.text
    data = resp.json()
    validate(data, "error")
    _assert_business_detail(data["detail"])

    # Sin transición: el log no gana entradas, L2 sigue sin verla y el recurso no cambia.
    assert len(get_request_log(requester_api, request_id)) == len(log_before)
    assert request_id not in received_ids(approver_l2_api)

    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]


def test_dos_niveles_doble_resolucion_409(admin_api, requester_api, api):
    """La doble resolución en L2 y cualquier actor en estado final reciben `409` sin transición."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    l1 = api(TOKENS["approver_l1"])
    l2 = api(TOKENS["approver_l2"])

    first_l1 = approve(l1, request_id)
    validate(first_l1, "request")
    assert first_l1["status"] == "approved_l1"
    log_after_l1 = get_request_log(requester_api, request_id)

    # En approved_l1 la visibilidad es de L2 (handoff §4.2): repetir approve L1 aquí no es
    # visible -> 404; el 409 del nivel solo aparece en estado final (abajo).
    retry_l1 = l1.post(f"/requests/{request_id}/approve")
    assert retry_l1.status_code == 404, retry_l1.text
    validate(retry_l1.json(), "error")
    _assert_business_detail(retry_l1.json()["detail"])
    assert len(get_request_log(requester_api, request_id)) == len(log_after_l1)

    final = approve(l2, request_id)
    validate(final, "request")
    assert final["status"] == "approved"
    log_final = get_request_log(requester_api, request_id)

    # Doble approve L2 -> 409.
    second_l2 = l2.post(f"/requests/{request_id}/approve")
    assert second_l2.status_code == 409, second_l2.text
    validate(second_l2.json(), "error")
    _assert_business_detail(second_l2.json()["detail"])

    # Estado final: cualquier actor recibe 409 aunque no tenga asignación al nivel vigente.
    outsider = api(TOKENS["override_l1"]).post(f"/requests/{request_id}/approve")
    assert outsider.status_code == 409, outsider.text
    validate(outsider.json(), "error")
    _assert_business_detail(outsider.json()["detail"])

    # El L1 original tampoco transiciona en estado final: 409, no 404.
    l1_final = l1.post(f"/requests/{request_id}/approve")
    assert l1_final.status_code == 409, l1_final.text
    validate(l1_final.json(), "error")

    assert len(get_request_log(requester_api, request_id)) == len(log_final)

    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}


def test_dos_niveles_basta_un_aprobador_por_nivel(
    admin_api, requester_api, approver_l2_api, api
):
    """Con [4,5]/[6] basta un aprobador por nivel: 5 aprueba L1, 6 aprueba L2 y el recurso se aplica."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    approver_l1_dos = api(TOKENS["approver_l1_dos"])
    assert request_id in received_ids(approver_l1_dos)
    assert request_id not in received_ids(approver_l2_api)

    # Basta uno de L1: resuelve 5, no 4.
    l1 = approve(approver_l1_dos, request_id)
    validate(l1, "request")
    assert l1["status"] == "approved_l1"

    # 4 (el otro L1) ya no participa; el turno pasa a L2.
    assert request_id not in received_ids(api(TOKENS["approver_l1"]))
    assert request_id in received_ids(approver_l2_api)

    l2 = approve(approver_l2_api, request_id)
    validate(l2, "request")
    assert l2["status"] == "approved"

    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}


def test_reconfigurar_flujo_no_altera_solicitud_en_vuelo(
    admin_api, requester_api, api
):
    """La foto L1 queda congelada al crear; la L2 se captura al aprobar L1 con la config vigente."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Foto L1 congelada: 4 y 5 la ven en pending; L2 no.
    assert request_id in received_ids(api(TOKENS["approver_l1"]))
    assert request_id in received_ids(api(TOKENS["approver_l1_dos"]))
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))

    # Reconfigurar el WS y el override del solicitante después de crear la solicitud.
    new_config = {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    }
    set_approvers(admin_api, approvers=new_config)
    set_approvers_override(admin_api, USER_IDS["requester"], new_config)

    # La asignación L1 no cambia: los nuevos (7) no la ven ni pueden resolverla.
    assert request_id not in received_ids(api(TOKENS["override_l1"]))
    assert request_id in received_ids(api(TOKENS["approver_l1"]))

    new_l1 = api(TOKENS["override_l1"]).post(f"/requests/{request_id}/approve")
    assert new_l1.status_code == 404, new_l1.text
    validate(new_l1.json(), "error")
    _assert_business_detail(new_l1.json()["detail"])

    # L1 original (4) resuelve; L2 se asigna con la config vigente en ese momento (8).
    l1 = approve(api(TOKENS["approver_l1"]), request_id)
    validate(l1, "request")
    assert l1["status"] == "approved_l1"

    assert request_id in received_ids(api(TOKENS["override_l2"]))
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))

    l2 = approve(api(TOKENS["override_l2"]), request_id)
    validate(l2, "request")
    assert l2["status"] == "approved"

    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}
