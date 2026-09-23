import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS
from helpers.flow import get_flow_config
from helpers.inbox import received_ids, sent_ids
from helpers.resources import get_resource
from schemas.validator import validate

pytestmark = pytest.mark.request

_RESOURCE_PATH = f"/resources/{CUENTA_PRINCIPAL['id']}/conciliar"


def _conciliar(requester_api, path: str, body: dict):
    return requester_api.post(path, json=body)


def test_conciliar_flujo_inactivo_aplica_directo_sin_solicitud(
    admin_api,
    requester_api,
    api,
):
    """S-07/AC-1.1: con el flujo inactivo, conciliar aplica por merge sin crear solicitud."""

    # Precondición C-002: el seed deja el flujo inactivo.
    assert get_flow_config(admin_api)["active"] is False

    resp = _conciliar(requester_api, _RESOURCE_PATH, {"changes": {"saldo": 777}})
    assert resp.status_code == 200, resp.text

    data = resp.json()
    validate(data, "resource")
    assert data["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 777}

    # Evidencia de negocio: el cambio quedó persistido en el recurso.
    confirm = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    assert confirm["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 777}

    # No se creó ninguna solicitud: nadie la recibe ni el solicitante la envió.
    l1_api = api(TOKENS["approver_l1"])
    l1_dos_api = api(TOKENS["approver_l1_dos"])
    l2_api = api(TOKENS["approver_l2"])
    assert received_ids(l1_api) == []
    assert received_ids(l1_dos_api) == []
    assert received_ids(l2_api) == []
    assert sent_ids(requester_api) == []


@pytest.mark.parametrize(
    "body",
    [
        {"changes": {"saldo": 777}},
        {"changes": {"saldo": 777}, "comment": ""},
        {"changes": {"saldo": 777}, "comment": "   "},
        {"changes": {"saldo": 777}, "comment": None},
    ],
    ids=["sin_comment", "comment_vacio", "comment_espacios", "comment_null"],
)
def test_conciliar_flujo_inactivo_ignora_comentario(requester_api, body):
    """AC-1.2/N-18: con el flujo inactivo el comentario se ignora (no se exige ni se valida)."""

    resp = _conciliar(requester_api, _RESOURCE_PATH, body)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    validate(data, "resource")
    assert data["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 777}

    confirm = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    assert confirm["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 777}


@pytest.mark.parametrize(
    "body",
    [
        {"changes": {}},
        {"comment": "x"},
    ],
    ids=["changes_vacio", "changes_ausente"],
)
def test_conciliar_flujo_inactivo_sin_cambios_no_altera(requester_api, body):
    """AC-1.3: `changes` vacío o ausente es un no-op: el recurso conserva los valores seed."""

    resp = _conciliar(requester_api, _RESOURCE_PATH, body)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    validate(data, "resource")
    assert data["values"] == CUENTA_PRINCIPAL["values"]

    confirm = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    assert confirm["values"] == CUENTA_PRINCIPAL["values"]


@pytest.mark.parametrize(
    "resource_id, expected_status",
    [
        (999, 404),
        (0, 404),
        (-1, 404),
        ("abc", 422),
    ],
    ids=["inexistente", "cero", "negativo", "no_entero"],
)
def test_conciliar_recurso_inexistente_o_malformado(
    requester_api, resource_id, expected_status
):
    """AC-1.4/N-10/N-11: recurso inexistente -> 404 (strings); path no entero -> 422 (dicts)."""

    resp = requester_api.post(
        f"/resources/{resource_id}/conciliar", json={"changes": {"saldo": 777}}
    )
    assert resp.status_code == expected_status, resp.text

    detail = resp.json()
    validate(detail, "error")
    if expected_status == 404:
        assert isinstance(detail["detail"], list)
        assert all(isinstance(item, str) for item in detail["detail"])
        assert str(resource_id) in " ".join(detail["detail"])
    else:
        assert isinstance(detail["detail"], list)
        assert all(isinstance(item, dict) for item in detail["detail"])
        assert any(item.get("type") == "int_parsing" for item in detail["detail"])

    # El recurso 1 no cambió por el intento fallido.
    assert get_resource(requester_api, CUENTA_PRINCIPAL["id"])["values"] == (
        CUENTA_PRINCIPAL["values"]
    )


@pytest.mark.parametrize(
    "body",
    [
        {"changes": None},
        {"changes": "saldo"},
        {"changes": []},
        {"comment": 123, "changes": {"saldo": 1}},
    ],
    ids=["changes_null", "changes_string", "changes_lista", "comment_numero"],
)
def test_conciliar_cuerpo_malformado_rechazado(requester_api, body):
    """AC-1.5/N-13: tipos erróneos -> 422 de validación (lista de dicts), sin coerción."""

    resp = _conciliar(requester_api, _RESOURCE_PATH, body)
    assert resp.status_code == 422, resp.text

    data = resp.json()
    validate(data, "error")
    assert isinstance(data["detail"], list)
    assert all(isinstance(item, dict) for item in data["detail"])

    # El rechazo no persiste estado: el recurso sigue en valores seed.
    assert get_resource(requester_api, CUENTA_PRINCIPAL["id"])["values"] == (
        CUENTA_PRINCIPAL["values"]
    )


def test_conciliar_extra_field_ignorado(requester_api):
    """AC-1.5: un campo extra en el body se ignora; se aplica solo lo declarado."""

    resp = _conciliar(
        requester_api,
        _RESOURCE_PATH,
        {"comment": "x", "changes": {"saldo": 1}, "extra": 1},
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    validate(data, "resource")
    assert data["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 1}
    assert "extra" not in data["values"]
    assert set(data["values"]) == set(CUENTA_PRINCIPAL["values"])

    confirm = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    assert confirm["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 1}
