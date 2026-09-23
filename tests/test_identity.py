import pytest

from data.payloads import conciliar
from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import activate_flow
from helpers.inbox import received_ids
from helpers.request_flow import approve, create_request, get_request_detail, get_request_log
from helpers.resources import get_resource, list_resources
from schemas.validator import validate

pytestmark = pytest.mark.default

# Flujo de 1 nivel: L1 = 4 y 5, sin L2.
APROBADORES_L1 = {
    "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
    "level_2": [],
}

# Los 10 endpoints del lote (sin /flow/*, cubiertos por C-001).
# (metodo, plantilla de path, body valido o None): {rid} = id de solicitud, {res} = id de recurso.
ENDPOINTS = [
    ("POST", "/resources/{res}/conciliar", conciliar({"saldo": 999})),
    ("POST", "/requests/{rid}/approve", None),
    ("POST", "/requests/{rid}/reject", None),
    ("POST", "/requests/{rid}/cancel", None),
    ("GET", "/requests/{rid}", None),
    ("GET", "/requests/{rid}/log", None),
    ("GET", "/inbox/received", None),
    ("GET", "/inbox/sent", None),
    ("GET", "/resources", None),
    ("GET", "/resources/{res}", None),
]

# Credencial invalida x detalle de negocio esperado (confirmado en vivo, handoff 8).
CREDENCIALES = [
    (None, "Credenciales requeridas"),
    ("token-inexistente", "Credenciales inválidas"),
    (TOKENS["inactive"], "Credenciales inválidas"),
]


@pytest.fixture
def valid_request_id(admin_api, requester_api) -> int:
    """Precondicion F-05: solicitud valida del solicitante, con id real, para la matriz 401."""

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
    return request_id


@pytest.mark.parametrize(("credential", "expected_detail"), CREDENCIALES)
@pytest.mark.parametrize(("method", "path_template", "body"), ENDPOINTS)
def test_endpoints_sin_token_o_invalido_401(
    api,
    admin_api,
    requester_api,
    valid_request_id,
    method,
    path_template,
    body,
    credential,
    expected_detail,
):
    """Sin token, con token inexistente o inactivo, los 10 endpoints del lote responden 401 con
    schema `error` y `detail` string de credenciales, antes que visibilidad o estado (S-28)."""

    request_id = valid_request_id
    path = path_template.format(rid=request_id, res=CUENTA_PRINCIPAL["id"])
    client = api(credential)
    kwargs = {"json": body} if body is not None else {}

    # Accion bajo prueba: misma ruta con credencial invalida.
    resp = client.get(path, **kwargs) if method == "GET" else client.post(path, **kwargs)

    # 1. Transporte: la identidad se resuelve antes que la visibilidad.
    assert resp.status_code == 401, resp.text
    # 2. Contrato.
    data = resp.json()
    validate(data, "error")
    # 3. Negocio: mensaje string de credenciales.
    assert isinstance(data["detail"], str) and data["detail"], data
    assert data["detail"] == expected_detail, data

    # Sin efectos: la solicitud sigue intacta (nunca aplicada) y el recurso conserva el seed.
    detail = get_request_detail(requester_api, request_id)
    validate(detail, "request_detail")
    assert detail["before"] == CUENTA_PRINCIPAL["values"]
    assert detail["applied"] == CUENTA_PRINCIPAL["values"]
    resource = get_resource(admin_api, CUENTA_PRINCIPAL["id"])
    validate(resource, "resource")
    assert resource["values"] == CUENTA_PRINCIPAL["values"]

    # Borde: con credencial valida la lectura sigue devolviendo sustancia (no un 200 vacio).
    resources = list_resources(admin_api)
    assert len(resources) == 3, resources
    assert get_resource(admin_api, CUENTA_PRINCIPAL["id"])["id"] == CUENTA_PRINCIPAL["id"]


def test_mismo_usuario_es_solicitante_y_aprobador(admin_api, requester_api, api):
    """El usuario 4 resuelve como aprobador la solicitud de 2 y es solicitante de otra que no
    recibe (excluido) y que resuelve 5; su `actor_name` coincide entre ambas y difiere del de 2
    (roles por contexto, AC-10.2)."""

    activate_flow(admin_api, levels=1, approvers=APROBADORES_L1)

    # Solicitud A: la crea 2 y la resuelve 4 como aprobador.
    created_a = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    validate(created_a, "request")
    a_id = created_a["id"]
    assert isinstance(a_id, int) and a_id > 0
    assert a_id in received_ids(api(TOKENS["approver_l1"]))

    resolved_a = approve(api(TOKENS["approver_l1"]), a_id)
    validate(resolved_a, "request")
    assert resolved_a["status"] == "approved"

    # Solicitud B: la crea el mismo usuario 4; como solicitante queda excluido y no la recibe.
    client_4 = api(TOKENS["approver_l1"])
    created_b = create_request(
        client_4,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 777},
    )
    validate(created_b, "request")
    b_id = created_b["id"]
    assert isinstance(b_id, int) and b_id > 0
    assert b_id not in received_ids(client_4)
    assert b_id in received_ids(api(TOKENS["approver_l1_dos"]))

    resolved_b = approve(api(TOKENS["approver_l1_dos"]), b_id)
    validate(resolved_b, "request")
    assert resolved_b["status"] == "approved"

    # actor_name: 4 como aprobador en A y como solicitante en B; distinto del de 2.
    log_a = get_request_log(requester_api, a_id)
    log_b = get_request_log(client_4, b_id)
    for entry in log_a + log_b:
        validate(entry, "request_log_entry")

    actor_4_approve = log_a[1]["actor_name"]
    actor_4_create = log_b[0]["actor_name"]
    actor_2_create = log_a[0]["actor_name"]
    assert isinstance(actor_4_approve, str) and actor_4_approve
    assert actor_4_approve == actor_4_create
    assert actor_4_approve != actor_2_create
