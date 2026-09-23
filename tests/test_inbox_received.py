import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow
from helpers.inbox import received_items
from helpers.request_flow import approve, cancel, create_request, reject
from schemas.validator import validate

pytestmark = pytest.mark.inbox

# Flujo de 2 niveles: L1 = 4 y 5, L2 = 6.
APROBADORES_2_NIVELES = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [USER_IDS["approver_l2"]],
}


def _item_recibido(items: list[dict], request_id: int) -> dict | None:
    """Valida el contrato de cada ítem de la bandeja y devuelve el de la solicitud, o None."""

    for item in items:
        validate(item, "inbox_item")
    return next((item for item in items if item["id"] == request_id), None)


@pytest.mark.regresion
def test_recibidas_visibilidad_por_estado(
    api, admin_api, requester_api, approver_l1_api, approver_l2_api
):
    """La bandeja de recibidas sigue el estado: pending solo para L1 (4 y 5), approved_l1 solo
    para L2 (6) y approved sigue en el último nivel (6); 4 y 5 dejan de verla al avanzar."""

    activate_flow(admin_api, levels=2, approvers=APROBADORES_2_NIVELES)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    l1 = api(TOKENS["approver_l1"])
    l1_dos = api(TOKENS["approver_l1_dos"])
    l2 = api(TOKENS["approver_l2"])

    # En pending la solicitud está en recibidas de los dos L1 y no en las de L2.
    item_4 = _item_recibido(received_items(l1), request_id)
    item_5 = _item_recibido(received_items(l1_dos), request_id)
    assert item_4 is not None and item_4["status"] == "pending", item_4
    assert item_5 is not None and item_5["status"] == "pending", item_5
    assert _item_recibido(received_items(l2), request_id) is None

    # Tras aprobar L1, la solicitud sale de 4/5 y pasa a 6.
    resolved_l1 = approve(approver_l1_api, request_id)
    validate(resolved_l1, "request")
    assert resolved_l1["status"] == "approved_l1"

    assert _item_recibido(received_items(l1), request_id) is None
    assert _item_recibido(received_items(l1_dos), request_id) is None
    item_6 = _item_recibido(received_items(l2), request_id)
    assert item_6 is not None and item_6["status"] == "approved_l1", item_6

    # Tras aprobar L2, 6 la sigue viendo como último nivel.
    resolved_l2 = approve(approver_l2_api, request_id)
    validate(resolved_l2, "request")
    assert resolved_l2["status"] == "approved"

    item_6_final = _item_recibido(received_items(l2), request_id)
    assert item_6_final is not None and item_6_final["status"] == "approved", item_6_final
    assert _item_recibido(received_items(l1), request_id) is None
    assert _item_recibido(received_items(l1_dos), request_id) is None


def test_recibidas_rechazada_en_l1_y_l2(
    api, admin_api, requester_api, approver_l1_api
):
    """Tras el rechazo en L1, la solicitud queda como rejected en recibidas de los L1 asignados
    (4 y 5) y nunca aparece en las de L2 (6); un aprobador válido no asignado (7) responde 200
    sin la solicitud."""

    activate_flow(admin_api, levels=2, approvers=APROBADORES_2_NIVELES)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Acción bajo prueba: 4 rechaza la solicitud todavía en L1.
    rejected = reject(approver_l1_api, request_id)
    validate(rejected, "request")
    assert rejected["status"] == "rejected"

    # Los L1 con asignación registrada conservan la solicitud resuelta.
    for token in (TOKENS["approver_l1"], TOKENS["approver_l1_dos"]):
        item = _item_recibido(received_items(api(token)), request_id)
        assert item is not None and item["status"] == "rejected", item

    # L2 nunca la vio (no hubo approved_l1 que le asignara el nivel).
    assert _item_recibido(received_items(api(TOKENS["approver_l2"])), request_id) is None

    # Un aprobador válido no asignado al nivel vigente responde 200 sin la solicitud.
    no_asignado = _item_recibido(received_items(api(TOKENS["override_l1"])), request_id)
    assert no_asignado is None, no_asignado


def test_recibidas_no_muestra_canceladas(api, admin_api, requester_api):
    """Una solicitud cancelada por el solicitante no aparece en la bandeja de recibidas de ningún
    aprobador (4, 5 ni 6); la lectura sigue respondiendo 200 con lista válida."""

    activate_flow(admin_api, levels=2, approvers=APROBADORES_2_NIVELES)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Acción bajo prueba: el solicitante 2 cancela su solicitud en pending.
    cancelled = cancel(requester_api, request_id)
    validate(cancelled, "request")
    assert cancelled["status"] == "cancelled"

    for token in (
        TOKENS["approver_l1"],
        TOKENS["approver_l1_dos"],
        TOKENS["approver_l2"],
    ):
        item = _item_recibido(received_items(api(token)), request_id)
        assert item is None, item
