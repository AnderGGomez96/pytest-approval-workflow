from datetime import datetime

import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow
from helpers.inbox import received_items, sent_ids, sent_items
from helpers.request_flow import approve, cancel, create_request, reject
from schemas.validator import validate

pytestmark = pytest.mark.inbox

APPROVERS = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [USER_IDS["approver_l2"]],
}


def _timestamp(item: dict) -> datetime:
    return datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))


@pytest.mark.regresion
def test_enviadas_incluye_siempre_mi_solicitud(
    admin_api,
    requester_api,
    approver_l1_api,
    approver_l2_api,
):
    """El solicitante ve su solicitud en enviadas en todos los estados; un aprobador no la ve."""
    activate_flow(admin_api, levels=2, approvers=APPROVERS)

    expected: dict[int, str] = {}

    pending = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 999}
    )
    expected[pending["id"]] = "pending"

    approved_l1 = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 998}
    )
    assert approve(approver_l1_api, approved_l1["id"])["status"] == "approved_l1"
    expected[approved_l1["id"]] = "approved_l1"

    approved = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 997}
    )
    assert approve(approver_l1_api, approved["id"])["status"] == "approved_l1"
    assert approve(approver_l2_api, approved["id"])["status"] == "approved"
    expected[approved["id"]] = "approved"

    rejected = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 996}
    )
    assert reject(approver_l1_api, rejected["id"])["status"] == "rejected"
    expected[rejected["id"]] = "rejected"

    cancelled = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 995}
    )
    assert cancel(requester_api, cancelled["id"])["status"] == "cancelled"
    expected[cancelled["id"]] = "cancelled"

    sent = sent_items(requester_api)
    assert len(sent) == len(expected)
    for item in sent:
        validate(item, "inbox_item")
    assert {item["id"]: item["status"] for item in sent} == expected

    # Un aprobador nunca ve la solicitud ajena en enviadas.
    assert not set(expected) & set(sent_ids(approver_l1_api))


def test_bandeja_vacia_devuelve_lista_vacia(
    admin_api,
    api,
    requester_api,
    approver_l1_api,
):
    """Un usuario sin solicitudes obtiene 200 []; una bandeja no vacía valida inbox_item."""
    activate_flow(admin_api, levels=2, approvers=APPROVERS)

    sin_solicitudes = api(TOKENS["requester_2"])
    assert sent_items(sin_solicitudes) == []
    assert received_items(sin_solicitudes) == []

    created = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 999}
    )

    sent = sent_items(requester_api)
    received = received_items(approver_l1_api)
    assert [item["id"] for item in sent] == [created["id"]]
    assert created["id"] in [item["id"] for item in received]
    for item in sent + received:
        validate(item, "inbox_item")


def test_bandejas_orden_pending_primero_y_mas_reciente(
    admin_api,
    requester_api,
    approver_l1_api,
):
    """Con estados mixtos en recibidas de L1, pending va primero y cada grupo por created_at desc."""
    activate_flow(admin_api, levels=2, approvers=APPROVERS)

    rechazada_1 = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 991}
    )
    pendiente_1 = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 992}
    )
    rechazada_2 = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 993}
    )
    pendiente_2 = create_request(
        requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes={"saldo": 994}
    )

    assert reject(approver_l1_api, rechazada_1["id"])["status"] == "rejected"
    assert reject(approver_l1_api, rechazada_2["id"])["status"] == "rejected"

    items = received_items(approver_l1_api)
    assert {item["id"] for item in items} == {
        rechazada_1["id"],
        pendiente_1["id"],
        rechazada_2["id"],
        pendiente_2["id"],
    }
    for item in items:
        validate(item, "inbox_item")

    pendientes = [item for item in items if item["status"] == "pending"]
    resto = [item for item in items if item["status"] != "pending"]
    assert len(pendientes) == 2
    assert len(resto) == 2

    # `pending` primero: ningún no-pending precede a un pending.
    statuses = [item["status"] for item in items]
    first_non_pending = next(
        (i for i, s in enumerate(statuses) if s != "pending"), len(statuses)
    )
    assert all(s == "pending" for s in statuses[:first_non_pending])
    assert all(s != "pending" for s in statuses[first_non_pending:])

    # Cada grupo (pending y no-pending) por created_at descendente, sin sub-agrupar por estado.
    for grupo in (pendientes, resto):
        marcas = [_timestamp(item) for item in grupo]
        assert marcas == sorted(marcas, reverse=True)
