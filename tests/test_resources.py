import pytest

from data.resources import CAJA_CHICA, CUENTA_PRINCIPAL, FONDO_RESERVA
from helpers.flow import activate_flow
from helpers.request_flow import approve, cancel, create_request, reject
from helpers.resources import get_resource, list_resources
from schemas.validator import validate

pytestmark = pytest.mark.default

_SEED = (CUENTA_PRINCIPAL, CAJA_CHICA, FONDO_RESERVA)
_PROPUESTO = {"saldo": 999}


@pytest.mark.smoke
def test_listado_recursos_seed(admin_api):
    """GET /resources devuelve los 3 recursos del seed y GET /resources/{id} coincide con el listado."""

    recursos = list_resources(admin_api)

    assert len(recursos) == len(_SEED)
    por_id = {recurso["id"]: recurso for recurso in recursos}

    # Cada recurso del seed aparece en el listado con su nombre y valores concretos (no un []).
    for sembrado in _SEED:
        assert sembrado["id"] in por_id
        entrada = por_id[sembrado["id"]]
        validate(entrada, "resource")
        assert entrada["name"] == sembrado["name"]
        assert entrada["values"] == sembrado["values"]
        assert entrada["values"], entrada

    # Evidencia de negocio: el detalle coincide en name/values con su entrada del listado.
    for sembrado in _SEED:
        entrada = por_id[sembrado["id"]]
        detalle = get_resource(admin_api, sembrado["id"])
        validate(detalle, "resource")
        assert detalle["name"] == entrada["name"]
        assert detalle["values"] == entrada["values"]

    # Sustancia: el saldo del seed es concreto, no un placeholder.
    assert por_id[CUENTA_PRINCIPAL["id"]]["values"]["saldo"] == CUENTA_PRINCIPAL["values"]["saldo"]


@pytest.mark.regresion
def test_recurso_refleja_aplicado_e_intacto(
    admin_api, requester_api, approver_l1_api, approver_l2_api
):
    """El recurso solo refleja el cambio tras approved; en pending/rejected/cancelled conserva el seed."""
    activate_flow(admin_api, levels=2)

    def assert_intacto(etapa):
        recurso = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
        validate(recurso, "resource")
        assert recurso["values"] == CUENTA_PRINCIPAL["values"], (etapa, recurso)
        assert recurso["values"]["saldo"] == CUENTA_PRINCIPAL["values"]["saldo"], etapa

    # pending: la solicitud propone el cambio pero el recurso sigue intacto.
    pendiente = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": _PROPUESTO["saldo"]},
    )
    validate(pendiente, "request")
    assert pendiente["status"] == "pending"
    assert_intacto("pending")

    # rejected: el rechazo en L1 descarta el cambio propuesto.
    rechazada = reject(approver_l1_api, pendiente["id"])
    validate(rechazada, "request")
    assert rechazada["status"] == "rejected"
    assert_intacto("rejected")

    # cancelled: la cancelación del solicitante tampoco aplica el cambio.
    cancelable = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": _PROPUESTO["saldo"]},
    )
    cancelada = cancel(requester_api, cancelable["id"])
    validate(cancelada, "request")
    assert cancelada["status"] == "cancelled"
    assert_intacto("cancelled")

    # approved: L1 no aplica; L2 aplica por merge conservando moneda y estado.
    aprobable = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": _PROPUESTO["saldo"]},
    )
    tras_l1 = approve(approver_l1_api, aprobable["id"])
    validate(tras_l1, "request")
    assert tras_l1["status"] == "approved_l1"
    assert_intacto("approved_l1")

    aprobada = approve(approver_l2_api, aprobable["id"])
    validate(aprobada, "request")
    assert aprobada["status"] == "approved"

    aplicado = get_resource(requester_api, CUENTA_PRINCIPAL["id"])
    validate(aplicado, "resource")
    assert aplicado["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": _PROPUESTO["saldo"]}
    assert aplicado["values"]["saldo"] == _PROPUESTO["saldo"]
    assert aplicado["values"]["moneda"] == CUENTA_PRINCIPAL["values"]["moneda"]
    assert aplicado["values"]["estado"] == CUENTA_PRINCIPAL["values"]["estado"]


@pytest.mark.parametrize(
    ("resource_id", "expected_status_code", "detail_format"),
    [
        (999, 404, "strings"),
        (0, 404, "strings"),
        (-1, 404, "strings"),
        ("abc", 422, "dicts"),
    ],
)
def test_recurso_inexistente_o_malformado(admin_api, resource_id, expected_status_code, detail_format):
    """Un id inexistente da 404 de negocio; un path no entero, 422 de validación; el seed no cambia."""

    resp = admin_api.get(f"/resources/{resource_id}")

    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail

    if detail_format == "strings":
        # Error de negocio: lista de strings que menciona el recurso pedido.
        assert all(isinstance(item, str) for item in detail), detail
        assert str(resource_id) in " ".join(detail), detail
    else:
        # Error de validación de FastAPI: lista de dicts (`int_parsing`).
        assert all(isinstance(item, dict) for item in detail), detail
        assert any(item.get("type") == "int_parsing" for item in detail), detail

    # Evidencia de negocio: el recurso 1 conserva los valores del seed (sin efecto del rechazo).
    intacto = get_resource(admin_api, CUENTA_PRINCIPAL["id"])
    validate(intacto, "resource")
    assert intacto["values"] == CUENTA_PRINCIPAL["values"]
