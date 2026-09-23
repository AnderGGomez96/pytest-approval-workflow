import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow, deactivate_flow
from helpers.inbox import received_ids, sent_items
from helpers.request_flow import (
    approve,
    cancel,
    create_request,
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


def test_cancelar_pending(admin_api, requester_api, api):
    """Cancelar una solicitud `pending` la deja `cancelled`, sin aplicar el recurso y sin
    mostrarla en las recibidas de ningún aprobador (S-21)."""

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

    # Precondición: en pending la ven los L1 (4 y 5); el L2 (6) todavía no.
    assert request_id in received_ids(api(TOKENS["approver_l1"]))
    assert request_id in received_ids(api(TOKENS["approver_l1_dos"]))
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))

    # Acción bajo prueba: el solicitante cancela su solicitud pendiente.
    cancelled = cancel(requester_api, request_id)

    validate(cancelled, "request")
    assert cancelled["id"] == request_id
    assert cancelled["status"] == "cancelled"
    assert cancelled["before"] == CUENTA_PRINCIPAL["values"]

    # Evidencia de negocio: el recurso nunca se aplica (valores seed exactos).
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    # Una cancelada nunca aparece en recibidas de aprobadores.
    assert request_id not in received_ids(api(TOKENS["approver_l1"]))
    assert request_id not in received_ids(api(TOKENS["approver_l1_dos"]))
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))

    # El solicitante la conserva en enviadas con el estado real.
    sent = {item["id"]: item for item in sent_items(requester_api)}
    assert sent[request_id]["status"] == "cancelled"

    # Log: pending -> cancelled con el actor del solicitante.
    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "cancelled"]
    assert log[1]["action"] == "cancel"
    assert log[1]["from_status"] == "pending"
    assert log[1]["actor_name"] == log[0]["actor_name"]


def test_cancelar_approved_l1(admin_api, requester_api, api):
    """Tras aprobar L1, el solicitante cancela sin pasar por L2: `cancelled`, el L2 deja de
    verla, el recurso sigue intacto y el log registra approved_l1 -> cancelled (S-21)."""

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

    # Precondición: aprobar L1 mueve la visibilidad a L2 (6).
    approved_l1 = approve(api(TOKENS["approver_l1"]), request_id)
    validate(approved_l1, "request")
    assert approved_l1["status"] == "approved_l1"
    assert request_id in received_ids(api(TOKENS["approver_l2"]))

    # Acción bajo prueba: el solicitante cancela en approved_l1 (no requiere L2).
    cancelled = cancel(requester_api, request_id)

    validate(cancelled, "request")
    assert cancelled["id"] == request_id
    assert cancelled["status"] == "cancelled"

    # Evidencia de negocio: el recurso permanece en valores seed (no se aplicó).
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    # El L2 deja de verla.
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))

    # Log: pending -> approved_l1 -> cancelled con el actor del solicitante en la cancelación.
    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "approved_l1", "cancelled"]
    assert log[2]["action"] == "cancel"
    assert log[2]["from_status"] == "approved_l1"
    assert log[2]["actor_name"] == log[0]["actor_name"]


@pytest.mark.parametrize(
    ("via", "final_status"),
    [
        # AC-6.3: alcanzar `approved` por su vía válida (L1 + L2).
        ("aprobar_l1_l2", "approved"),
        # AC-6.3: alcanzar `rejected` por su vía válida (rechazo L1).
        ("rechazar_l1", "rejected"),
        # AC-6.6 / N-15: la doble cancelación deja `cancelled` como estado final.
        ("cancelar", "cancelled"),
    ],
)
def test_cancelar_en_estado_final_409(admin_api, requester_api, api, via, final_status):
    """Cancelar sobre `approved`, `rejected` o `cancelled` da 409 sin transición ni efecto
    (N-14/N-15)."""

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

    # Precondición: alcanzar el estado final por su vía válida.
    if via == "aprobar_l1_l2":
        approve(api(TOKENS["approver_l1"]), request_id)
        resolved = approve(api(TOKENS["approver_l2"]), request_id)
    elif via == "rechazar_l1":
        resolved = reject(api(TOKENS["approver_l1"]), request_id)
    else:
        resolved = cancel(requester_api, request_id)
    validate(resolved, "request")
    assert resolved["status"] == final_status

    log_before = get_request_log(requester_api, request_id)
    resource_before = get_resource(requester_api, CUENTA_PRINCIPAL["id"])["values"]

    # Acción bajo prueba: cancelar una solicitud ya en estado final.
    resp = requester_api.post(f"/requests/{request_id}/cancel")

    assert resp.status_code == 409, resp.text
    data = resp.json()
    validate(data, "error")
    detail = data["detail"]
    _assert_business_detail(detail)
    assert final_status in " ".join(detail), detail

    # Sin transición: el log conserva exactamente las mismas entradas.
    log_after = get_request_log(requester_api, request_id)
    assert len(log_after) == len(log_before)
    assert [entry["to_status"] for entry in log_after] == [
        entry["to_status"] for entry in log_before
    ]

    # Sin efecto: el recurso no cambia por el intento rechazado.
    assert get_resource(requester_api, CUENTA_PRINCIPAL["id"])["values"] == resource_before


def test_cancelar_por_otro_usuario_403(admin_api, requester_api, api):
    """Solo el solicitante cancela: un aprobador asignado (4) recibe 403 y un tercero (3) 404;
    la solicitud sigue pending y cancelable por 2 (S-22)."""

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

    # Acción bajo prueba: 4 (aprobador L1 asignado, con visibilidad) intenta cancelar.
    resp = api(TOKENS["approver_l1"]).post(f"/requests/{request_id}/cancel")

    assert resp.status_code == 403, resp.text
    data = resp.json()
    validate(data, "error")
    detail = data["detail"]
    _assert_business_detail(detail)
    assert "solo el solicitante" in " ".join(detail), detail

    # Acción bajo prueba: 3 (tercero, sin visibilidad) intenta cancelar.
    resp = api(TOKENS["requester_2"]).post(f"/requests/{request_id}/cancel")

    assert resp.status_code == 404, resp.text
    data = resp.json()
    validate(data, "error")
    _assert_business_detail(data["detail"])

    # Sin transición: la solicitud sigue pending y el recurso intacto.
    sent = {item["id"]: item for item in sent_items(requester_api)}
    assert sent[request_id]["status"] == "pending"
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    # Evidencia de negocio: el solicitante sí puede cancelarla.
    cancelled = cancel(requester_api, request_id)
    validate(cancelled, "request")
    assert cancelled["status"] == "cancelled"


@pytest.mark.parametrize(
    ("request_id", "expected_status"),
    [
        (999, 404),
        (0, 404),
        (-1, 404),
        ("abc", 422),
    ],
)
def test_cancelar_id_invalido(admin_api, requester_api, request_id, expected_status):
    """Cancelar con un id inexistente da 404 (lista de strings) y con un path no entero 422
    (lista de dicts), nunca 500 (N-10/N-11)."""

    activate_flow(admin_api, levels=2, approvers=WORKSPACE_2_LEVELS)

    # Acción bajo prueba: POST directo con el path inválido parametrizado.
    resp = requester_api.post(f"/requests/{request_id}/cancel")

    assert resp.status_code == expected_status, resp.text
    data = resp.json()
    validate(data, "error")
    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail

    if expected_status == 404:
        # Error de negocio: lista de strings que menciona la solicitud.
        assert all(isinstance(item, str) for item in detail), detail
        assert str(request_id) in " ".join(detail), detail
    else:
        # Error de validación de FastAPI: lista de dicts (`int_parsing`).
        assert all(isinstance(item, dict) for item in detail), detail


def test_cancelar_con_flujo_desactivado(admin_api, requester_api):
    """Desactivar el flujo con la solicitud en vuelo no impide al solicitante cancelarla
    (desactivar no cancela; N-16)."""

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

    # Acción bajo prueba: desactivar el flujo con la solicitud en vuelo.
    deactivate_flow(admin_api)

    # La desactivación no altera el estado de la solicitud.
    sent = {item["id"]: item for item in sent_items(requester_api)}
    assert sent[request_id]["status"] == "pending"

    # El solicitante la cancela igual: 200 `cancelled`.
    cancelled = cancel(requester_api, request_id)
    validate(cancelled, "request")
    assert cancelled["id"] == request_id
    assert cancelled["status"] == "cancelled"

    # El recurso permanece intacto y el log registra pending -> cancelled.
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "cancelled"]
    assert log[1]["action"] == "cancel"
    assert log[1]["from_status"] == "pending"
