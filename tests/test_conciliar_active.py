import pytest

from data.payloads import conciliar
from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow
from helpers.inbox import received_ids, sent_ids
from helpers.request_flow import create_request, get_request_log
from helpers.resources import get_resource
from schemas.validator import validate

pytestmark = pytest.mark.request

_ACTIVO_2_NIVELES = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [USER_IDS["approver_l2"]],
}
_ACTIVO_1_NIVEL = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [],
}
_COMENTARIO = "ajuste de prueba"
_CAMBIOS = {"saldo": 999}
_CONCILIAR_PATH = f"/resources/{CUENTA_PRINCIPAL['id']}/conciliar"
_NEGOCIO_COMENTARIO = "el comentario no puede estar vacio"


def _assert_recurso_intacto(client):
    """El recurso 1 conserva los valores seed mientras la solicitud esta en vuelo (S-11)."""
    resource = get_resource(client, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]


def _assert_sin_solicitud(api, requester_api):
    """Ninguna bandeja registra una solicitud: la creacion rechazada no persiste nada."""
    assert sent_ids(requester_api) == []
    for token in (TOKENS["approver_l1"], TOKENS["approver_l1_dos"], TOKENS["approver_l2"]):
        assert received_ids(api(token)) == []


def test_conciliar_flujo_activo_crea_solicitud_pendiente(admin_api, requester_api):
    """Con 2 niveles activo el conciliar crea una solicitud `pending` con before/proposed exactos y
    deja el recurso intacto (AC-2.1, S-08/S-09/S-11)."""

    activate_flow(admin_api, levels=2, approvers=_ACTIVO_2_NIVELES)

    # Accion bajo prueba: el solicitante concilia con el flujo activo (create_request afirma el 201).
    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes=_CAMBIOS,
        comment=_COMENTARIO,
    )

    validate(created, "request")
    assert created["status"] == "pending"
    assert isinstance(created["id"], int) and created["id"] > 0
    assert created["before"] == CUENTA_PRINCIPAL["values"]
    assert created["proposed"] == _CAMBIOS
    assert created["comment"] == _COMENTARIO

    # Evidencia de negocio: el recurso no se aplica mientras la solicitud esta pendiente.
    _assert_recurso_intacto(requester_api)


def test_conciliar_flujo_activo_un_nivel_crea_solicitud(admin_api, requester_api):
    """Con 1 nivel activo `[4,5]/[]` la creacion tambien es `201 pending` y el recurso sigue intacto
    (AC-2.2)."""

    activate_flow(admin_api, levels=1, approvers=_ACTIVO_1_NIVEL)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes=_CAMBIOS,
        comment=_COMENTARIO,
    )

    validate(created, "request")
    assert created["status"] == "pending"
    assert isinstance(created["id"], int) and created["id"] > 0
    assert created["before"] == CUENTA_PRINCIPAL["values"]
    assert created["proposed"] == _CAMBIOS
    assert created["comment"] == _COMENTARIO

    _assert_recurso_intacto(requester_api)


@pytest.mark.parametrize(
    "body",
    [
        {"changes": _CAMBIOS},
        {"comment": "", "changes": _CAMBIOS},
        {"comment": "   ", "changes": _CAMBIOS},
        {"comment": "\t", "changes": _CAMBIOS},
        {"comment": "\n", "changes": _CAMBIOS},
        {"comment": None, "changes": _CAMBIOS},
    ],
)
def test_conciliar_flujo_activo_comentario_vacio_rechazado(admin_api, api, requester_api, body):
    """Con el flujo activo el comentario es obligatorio no vacio: ausente, vacio/solo espacios/tab/
    salto o `null` se rechaza con `detail` lista de strings y no crea solicitud (AC-2.4/2.5, S-10,
    N-12)."""

    activate_flow(admin_api, levels=2, approvers=_ACTIVO_2_NIVELES)

    # Accion bajo prueba: POST directo con el body crudo parametrizado.
    resp = requester_api.post(_CONCILIAR_PATH, json=body)

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    # Rechazo de negocio: lista de strings, no de dicts (contrato FastAPI).
    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail
    assert all(isinstance(item, str) for item in detail), detail
    assert any("comentario" in item for item in detail), detail

    # Evidencia de negocio: el rechazo no persiste ninguna solicitud ni toca el recurso.
    _assert_sin_solicitud(api, requester_api)
    _assert_recurso_intacto(requester_api)


def test_conciliar_comentario_valido_se_conserva(admin_api, requester_api):
    """El comentario valido se conserva exacto (acentos y espacios internos) y la creacion deja una
    unica entrada de log `create -> pending` (AC-2.3)."""

    activate_flow(admin_api, levels=2, approvers=_ACTIVO_2_NIVELES)

    comment = "Reajuste  de  saldo — cafe, nandu y  espacios"
    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes=_CAMBIOS,
        comment=comment,
    )

    validate(created, "request")
    assert created["comment"] == comment

    # La entidad `request_log_entry` no declara el comentario (handoff F-04): se afirma la forma
    # de la creacion y la conservacion del texto en la respuesta de la solicitud.
    log = get_request_log(requester_api, created["id"])
    assert len(log) == 1
    for entry in log:
        validate(entry, "request_log_entry")
    assert log[0]["action"] == "create"
    assert log[0]["from_status"] is None
    assert log[0]["to_status"] == "pending"


@pytest.mark.parametrize(
    "body",
    [
        {"comment": 123, "changes": _CAMBIOS},
        {"comment": "x", "changes": None},
        {"comment": "x", "changes": "saldo"},
        {"comment": "x", "changes": []},
    ],
)
def test_conciliar_flujo_activo_campos_malformados_rechazado(admin_api, requester_api, body):
    """`comment` numerico o `changes` null/string/lista se rechazan como validacion de contrato
    (`detail` lista de dicts) sin crear solicitud (AC-2.5, N-13)."""

    activate_flow(admin_api, levels=2, approvers=_ACTIVO_2_NIVELES)

    # Accion bajo prueba: POST directo con el body crudo malformado.
    resp = requester_api.post(_CONCILIAR_PATH, json=body)

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    # Error de validacion de FastAPI: `detail` es lista de dicts, no de strings.
    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail
    assert all(isinstance(item, dict) for item in detail), detail

    # Evidencia de negocio: el cuerpo invalido no crea nada.
    assert sent_ids(requester_api) == []
    _assert_recurso_intacto(requester_api)


def test_conciliar_flujo_activo_changes_vacio_crea_solicitud(admin_api, requester_api):
    """`changes:{}` con el flujo activo crea la solicitud `pending` con `proposed == {}`: el contrato
    no exige cambios (AC-2.5, N-17)."""

    activate_flow(admin_api, levels=2, approvers=_ACTIVO_2_NIVELES)

    # Accion bajo prueba: POST directo porque el helper `create_request` repone el default de cambios.
    resp = requester_api.post(_CONCILIAR_PATH, json={"comment": "x", "changes": {}})

    assert resp.status_code == 201, resp.text
    data = resp.json()
    validate(data, "request")
    assert data["status"] == "pending"
    assert isinstance(data["id"], int) and data["id"] > 0
    assert data["proposed"] == {}
    assert data["before"] == CUENTA_PRINCIPAL["values"]
    assert data["comment"] == "x"

    _assert_recurso_intacto(requester_api)


def test_conciliar_flujo_activo_extra_field_ignorado(admin_api, requester_api):
    """Un campo extra en el body con el resto valido se tolera: crea la solicitud aplicando solo
    `comment`/`changes` (AC-2.7)."""

    activate_flow(admin_api, levels=2, approvers=_ACTIVO_2_NIVELES)

    # Accion bajo prueba: POST directo con un campo extra no declarado.
    body = {"comment": "ajuste", "changes": _CAMBIOS, "extra": 1}
    resp = requester_api.post(_CONCILIAR_PATH, json=body)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    validate(data, "request")
    assert data["status"] == "pending"
    assert set(data["proposed"]) == {"saldo"}
    assert data["proposed"] == _CAMBIOS
    assert data["comment"] == "ajuste"

    _assert_recurso_intacto(requester_api)


@pytest.mark.parametrize(
    ("resource_path", "expected_status", "validation_detail"),
    [
        ("999", 404, False),
        ("abc", 422, True),
    ],
)
def test_conciliar_flujo_activo_recurso_inexistente_no_crea(
    admin_api, requester_api, resource_path, expected_status, validation_detail
):
    """Con el flujo activo un recurso inexistente da `404` (lista de strings) y un path no entero
    `422` (lista de dicts), sin crear solicitud ni tocar el recurso 1 (AC-2.6, N-10/N-11)."""

    activate_flow(admin_api, levels=2, approvers=_ACTIVO_2_NIVELES)

    # Accion bajo prueba: POST con path inexistente o malformado.
    resp = requester_api.post(
        f"/resources/{resource_path}/conciliar",
        json=conciliar(_CAMBIOS, _COMENTARIO),
    )

    assert resp.status_code == expected_status, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail
    if validation_detail:
        assert all(isinstance(item, dict) for item in detail), detail
    else:
        assert all(isinstance(item, str) for item in detail), detail
        assert any(resource_path in item for item in detail), detail

    # Evidencia de negocio: no se crea solicitud y el recurso 1 sigue con los valores seed.
    assert sent_ids(requester_api) == []
    _assert_recurso_intacto(requester_api)
