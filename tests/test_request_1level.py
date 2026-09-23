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
    reject,
)
from helpers.resources import get_resource
from schemas.validator import validate

pytestmark = pytest.mark.request

# Flujo de 1 nivel con los dos aprobadores L1 del workspace (4 y 5).
APROBADORES_L1 = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [],
}


@pytest.mark.regresion
def test_un_nivel_aprobar_aplica_por_merge(admin_api, requester_api, approver_l1_api):
    """Aprobar en 1 nivel aplica el cambio por merge, el detalle refleja el applied y el log
    registra pending -> approved con el actor real."""

    activate_flow(admin_api, levels=1, approvers=APROBADORES_L1)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Acción bajo prueba: 4 aprueba la solicitud pendiente.
    resolved = approve(approver_l1_api, request_id)

    validate(resolved, "request")
    assert resolved["id"] == request_id
    assert resolved["status"] == "approved"

    # Evidencia de negocio: el recurso queda aplicado por merge (conserva moneda y estado).
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}

    # El detalle pasa a applied == merge, con before/proposed intactos.
    detail = get_request_detail(requester_api, request_id)
    validate(detail, "request_detail")
    assert detail["before"] == CUENTA_PRINCIPAL["values"]
    assert detail["proposed"] == {"saldo": 999}
    assert detail["applied"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}

    # El log registra la transición con el actor real (4, distinto del solicitante 2).
    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "approved"]
    assert log[1]["action"] == "approve"
    assert log[1]["from_status"] == "pending"
    assert isinstance(log[1]["actor_name"], str) and log[1]["actor_name"]
    assert log[1]["actor_name"] != log[0]["actor_name"]


@pytest.mark.regresion
def test_un_nivel_rechazar_no_aplica(admin_api, requester_api, approver_l1_api):
    """Rechazar en 1 nivel deja el recurso intacto y el log registra pending -> rejected."""

    activate_flow(admin_api, levels=1, approvers=APROBADORES_L1)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Acción bajo prueba: 4 rechaza la solicitud pendiente.
    resolved = reject(approver_l1_api, request_id)

    validate(resolved, "request")
    assert resolved["id"] == request_id
    assert resolved["status"] == "rejected"

    # Evidencia de negocio: el recurso nunca se aplica (valores seed exactos).
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    # El detalle mantiene applied == before, con el proposed intacto.
    detail = get_request_detail(requester_api, request_id)
    validate(detail, "request_detail")
    assert detail["before"] == CUENTA_PRINCIPAL["values"]
    assert detail["proposed"] == {"saldo": 999}
    assert detail["applied"] == CUENTA_PRINCIPAL["values"]

    # El log registra la transición con el actor real (4).
    log = get_request_log(requester_api, request_id)
    for entry in log:
        validate(entry, "request_log_entry")
    assert [entry["to_status"] for entry in log] == ["pending", "rejected"]
    assert log[1]["action"] == "reject"
    assert log[1]["from_status"] == "pending"
    assert isinstance(log[1]["actor_name"], str) and log[1]["actor_name"]
    assert log[1]["actor_name"] != log[0]["actor_name"]


@pytest.mark.parametrize(
    ("actor_token", "other_token", "action", "expected_status", "aplica"),
    [
        # AC-3.3: cualquiera de los dos L1 resuelve; tras aprobar 4, 5 sigue viéndola resuelta.
        (TOKENS["approver_l1"], TOKENS["approver_l1_dos"], "approve", "approved", True),
        # AC-3.6: el segundo aprobador también puede rechazar mientras está pending.
        (TOKENS["approver_l1_dos"], TOKENS["approver_l1"], "reject", "rejected", False),
    ],
)
def test_un_nivel_varios_aprobadores_basta_uno(
    api, admin_api, requester_api, actor_token, other_token, action, expected_status, aplica
):
    """Con varios aprobadores L1 basta uno para resolver; el otro ve la solicitud ya resuelta."""

    activate_flow(admin_api, levels=1, approvers=APROBADORES_L1)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Precondición: ambos aprobadores L1 reciben la solicitud pendiente.
    assert request_id in received_ids(api(actor_token))
    assert request_id in received_ids(api(other_token))

    # Acción bajo prueba: uno solo de los dos la resuelve.
    actor = api(actor_token)
    resolved = approve(actor, request_id) if action == "approve" else reject(actor, request_id)

    validate(resolved, "request")
    assert resolved["status"] == expected_status

    # Evidencia de negocio: aprobar aplica por merge; rechazar deja el recurso intacto.
    resource = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    if aplica:
        assert resource["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}
    else:
        assert resource["values"] == CUENTA_PRINCIPAL["values"]

    # El otro aprobador sigue viendo la solicitud resuelta en recibidas (último nivel L1).
    assert request_id in received_ids(api(other_token))


def test_un_nivel_aprobador_no_asignado_404(admin_api, requester_api, approver_l2_api):
    """Un aprobador no asignado al nivel vigente (6 en 1 nivel) recibe 404 sin transición."""

    activate_flow(admin_api, levels=1, approvers=APROBADORES_L1)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    log_before = get_request_log(requester_api, request_id)

    # Acción bajo prueba: 6 intenta aprobar sin estar asignado.
    resp = approver_l2_api.post(f"/requests/{request_id}/approve")

    assert resp.status_code == 404, resp.text
    data = resp.json()
    validate(data, "error")
    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail
    assert all(isinstance(item, str) for item in detail), detail
    assert str(request_id) in " ".join(detail), detail

    # Sin transición: el log no gana entradas y la solicitud sigue pending.
    log_after = get_request_log(requester_api, request_id)
    assert len(log_after) == len(log_before)
    assert log_after[-1]["to_status"] == "pending"


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.regresion
def test_solicitante_no_resuelve_su_solicitud(
    admin_api, requester_api, approver_l1_api, action
):
    """El solicitante, aunque sea aprobador L1, no resuelve su propia solicitud: 403 y sigue
    pending; otro aprobador sí la resuelve (S-19)."""

    # Precondición: el solicitante 2 figura junto a 4 en el conjunto efectivo de L1.
    activate_flow(
        admin_api,
        levels=1,
        approvers={
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

    log_before = get_request_log(requester_api, request_id)
    assert [entry["to_status"] for entry in log_before] == ["pending"]

    # Acción bajo prueba: 2 intenta resolver su propia solicitud.
    resp = requester_api.post(f"/requests/{request_id}/{action}")

    assert resp.status_code == 403, resp.text
    data = resp.json()
    validate(data, "error")
    assert isinstance(data["detail"], str) and data["detail"]

    # Sin transición: sigue pending y el log no gana entradas.
    log_after = get_request_log(requester_api, request_id)
    assert len(log_after) == len(log_before)
    assert log_after[-1]["to_status"] == "pending"

    # Evidencia de negocio: 4 (excluido el solicitante) sí la resuelve.
    resolved = approve(approver_l1_api, request_id)
    validate(resolved, "request")
    assert resolved["status"] == "approved"


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize(
    ("request_id", "expected_status"),
    [
        (999, 404),
        (0, 404),
        (-1, 404),
        ("abc", 422),
    ],
)
def test_resolver_solicitud_id_invalido(
    admin_api, approver_l1_api, action, request_id, expected_status
):
    """Resolver con un id inexistente da 404 (lista de strings) y con un path no entero 422
    (lista de dicts), nunca 500 (N-10/N-11)."""

    activate_flow(admin_api, levels=1, approvers=APROBADORES_L1)

    # Acción bajo prueba: POST directo con el path inválido parametrizado.
    resp = approver_l1_api.post(f"/requests/{request_id}/{action}")

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


@pytest.mark.parametrize(
    ("first_action", "final_status"),
    [
        ("approve", "approved"),
        ("reject", "rejected"),
    ],
)
@pytest.mark.regresion
def test_doble_resolucion_409(
    api, admin_api, requester_api, approver_l1_api, first_action, final_status
):
    """Repetir la resolución (mismo actor o el otro aprobador) sobre un estado final da 409 sin
    nueva transición en el log (AC-3.5, N-14)."""

    activate_flow(admin_api, levels=1, approvers=APROBADORES_L1)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created, "request")
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Precondición: alcanzar el estado final por la vía válida.
    resolved = (
        approve(approver_l1_api, request_id)
        if first_action == "approve"
        else reject(approver_l1_api, request_id)
    )
    validate(resolved, "request")
    assert resolved["status"] == final_status

    log_before = get_request_log(requester_api, request_id)
    assert [entry["to_status"] for entry in log_before] == ["pending", final_status]

    # Acción bajo prueba: mismo actor y el otro aprobador repiten la acción.
    for actor in (approver_l1_api, api(TOKENS["approver_l1_dos"])):
        resp = actor.post(f"/requests/{request_id}/{first_action}")

        assert resp.status_code == 409, resp.text
        data = resp.json()
        validate(data, "error")
        detail = data["detail"]
        assert isinstance(detail, list) and detail, detail
        assert all(isinstance(item, str) for item in detail), detail
        assert final_status in " ".join(detail), detail

    # Sin transición: el log conserva exactamente las mismas entradas.
    log_after = get_request_log(requester_api, request_id)
    assert len(log_after) == len(log_before)
    assert [entry["to_status"] for entry in log_after] == ["pending", final_status]
