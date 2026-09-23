import pytest

from data.payloads import approvers_config, flow_config
from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS, USER_IDS
from helpers.flow import (
    activate_flow,
    get_flow_approvers,
    get_flow_config,
    get_flow_overrides,
    set_approvers,
    set_approvers_override,
)
from helpers.inbox import received_ids, sent_ids
from helpers.request_flow import approve, create_request
from schemas.validator import validate

pytestmark = pytest.mark.flow


def test_put_flow_approvers_admin_define_y_get_confirma(admin_api):
    """El admin define aprobadores por nivel y el GET devuelve lo mismo."""

    # Acción bajo prueba: set_approvers afirma su 200 con resp.text.
    data = set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    })

    validate(data, "flow_approvers")
    assert data["level_1"] == [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]]
    assert data["level_2"] == [USER_IDS["approver_l2"]]

    # Evidencia de negocio: el GET confirma ambos niveles (no un vacío).
    confirm = get_flow_approvers(admin_api)

    validate(confirm, "flow_approvers")
    assert confirm["level_1"] == [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]]
    assert confirm["level_2"] == [USER_IDS["approver_l2"]]


def test_put_flow_approvers_reemplaza_listas(admin_api):
    """Un PUT reemplaza las listas de aprobadores, no las acumula."""

    set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    })

    # Acción bajo prueba: se encoge L1 y se vacía L2.
    data = set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"]],
        "level_2": [],
    })

    validate(data, "flow_approvers")
    assert data["level_1"] == [USER_IDS["approver_l1"]]
    assert data["level_2"] == []

    # Evidencia de negocio: no queda rastro de [5] ni de [6].
    confirm = get_flow_approvers(admin_api)

    validate(confirm, "flow_approvers")
    assert confirm["level_1"] == [USER_IDS["approver_l1"]]
    assert confirm["level_2"] == []


def test_put_flow_approvers_vacio_permitido(admin_api):
    """Configurar sin aprobadores es válido: solo activar el flujo los exige."""

    # Acción bajo prueba: ambas listas vacías.
    data = set_approvers(admin_api, approvers={"level_1": [], "level_2": []})

    validate(data, "flow_approvers")
    assert data["level_1"] == []
    assert data["level_2"] == []

    # Evidencia de negocio: el GET devuelve las listas vacías.
    confirm = get_flow_approvers(admin_api)

    validate(confirm, "flow_approvers")
    assert confirm["level_1"] == []
    assert confirm["level_2"] == []


@pytest.mark.parametrize(
    ("token", "expected_status_code", "detail"),
    [
        (None, 401, None),
        (TOKENS["inactive"], 401, None),
        (TOKENS["requester"], 403, "Requiere administrador"),
        (TOKENS["approver_l1"], 403, "Requiere administrador"),
        (TOKENS["approver_l2"], 403, "Requiere administrador"),
        (TOKENS["admin"], 200, None),
    ],
)
def test_put_flow_approvers_roles(api, admin_api, token, expected_status_code, detail):
    """Solo el admin define aprobadores; el resto recibe 401/403 sin alterar el seed."""

    approvers = {
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    }

    # Acción bajo prueba: PUT directo con el cliente del rol parametrizado.
    resp = api(token).put("/flow/approvers", json=approvers_config(approvers))

    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()

    if expected_status_code == 200:
        validate(data, "flow_approvers")
        assert data["level_1"] == approvers["level_1"]
        assert data["level_2"] == approvers["level_2"]

        confirm = get_flow_approvers(admin_api)
        validate(confirm, "flow_approvers")
        assert confirm["level_1"] == approvers["level_1"]
        assert confirm["level_2"] == approvers["level_2"]
    else:
        validate(data, "error")
        if detail is not None:
            assert data["detail"] == detail

        # Evidencia de negocio: el rechazo deja intacto el seed ([]/[]).
        unchanged = get_flow_approvers(admin_api)
        validate(unchanged, "flow_approvers")
        assert unchanged["level_1"] == []
        assert unchanged["level_2"] == []


def test_put_flow_config_dos_niveles_activo(admin_api):
    """El admin activa el flujo de 2 niveles con aprobadores y el GET lo confirma."""

    set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    })

    # Acción bajo prueba: activar 2 niveles.
    resp = admin_api.put("/flow/config", json=flow_config(levels=2, active=True))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    validate(data, "flow_config")
    assert data == {"levels": 2, "active": True}

    # Evidencia de negocio: el GET confirma la configuración activa.
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 2, "active": True}


def test_put_flow_config_un_nivel_activo(admin_api):
    """El admin activa el flujo de 1 nivel con solo aprobadores L1 y el GET lo confirma."""

    set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [],
    })

    # Acción bajo prueba: activar 1 nivel (L2 no requerido).
    resp = admin_api.put("/flow/config", json=flow_config(levels=1, active=True))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    validate(data, "flow_config")
    assert data == {"levels": 1, "active": True}

    # Evidencia de negocio: el GET confirma la configuración activa.
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 1, "active": True}


def test_put_flow_config_desactivar_sin_aprobadores(admin_api):
    """Desactivar el flujo no exige aprobadores: el GET confirma el estado inactivo."""

    # Acción bajo prueba: desactivar sin haber configurado aprobadores.
    resp = admin_api.put("/flow/config", json=flow_config(levels=2, active=False))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    validate(data, "flow_config")
    assert data == {"levels": 2, "active": False}

    # Evidencia de negocio: el GET confirma la configuración inactiva.
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 2, "active": False}


@pytest.mark.parametrize(
    ("approvers", "levels", "missing_levels"),
    [
        # Sin aprobadores en ningún nivel: faltan ambos.
        ({"level_1": [], "level_2": []}, 2, ["nivel 1 sin aprobadores", "nivel 2 sin aprobadores"]),
        # L1 configurado pero L2 vacío: falta el nivel 2.
        ({"level_1": [USER_IDS["approver_l1"]], "level_2": []}, 2, ["nivel 2 sin aprobadores"]),
        # 1 nivel con L1 vacío: falta el nivel 1.
        ({"level_1": [], "level_2": []}, 1, ["nivel 1 sin aprobadores"]),
    ],
)
def test_put_flow_config_activo_sin_aprobadores_422(admin_api, approvers, levels, missing_levels):
    """Activar el flujo sin aprobadores en un nivel requerido se rechaza sin persistir."""

    set_approvers(admin_api, approvers=approvers)

    # Acción bajo prueba: activar el flujo con niveles sin aprobadores.
    resp = admin_api.put("/flow/config", json=flow_config(levels, active=True))

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")
    assert data["detail"] == missing_levels

    # Evidencia de negocio: el rechazo no persiste nada (el seed sigue inactivo).
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 2, "active": False}


@pytest.mark.parametrize("levels", [0, 3])
def test_put_flow_config_levels_invalido_422(admin_api, levels):
    """Un `levels` fuera de {1, 2} es un error de contrato y no persiste."""

    # Acción bajo prueba: `levels` inválido.
    resp = admin_api.put("/flow/config", json=flow_config(levels, active=True))

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    # Error de validación de FastAPI: `detail` es lista de dicts, no de strings.
    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail
    assert all(isinstance(item, dict) for item in detail), detail

    # Evidencia de negocio: la configuración previa no cambia (el seed sigue inactivo).
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 2, "active": False}


@pytest.mark.request
def test_put_flow_config_desactivar_no_cancela_solicitud_en_vuelo(
    admin_api, requester_api, approver_l1_api, approver_l2_api
):
    """Desactivar el flujo no cancela una solicitud en vuelo: se resuelve igual y el recurso se aplica por merge."""

    set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    })
    activated = admin_api.put("/flow/config", json=flow_config(levels=2, active=True))
    assert activated.status_code == 200, activated.text

    # Precondición: solicitud creada con el flujo activo.
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
    resp = admin_api.put("/flow/config", json=flow_config(levels=2, active=False))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    validate(data, "flow_config")
    assert data == {"levels": 2, "active": False}

    # Evidencia de negocio: la solicitud no queda cancelada, se resuelve L1 y L2.
    l1 = approve(approver_l1_api, request_id)
    assert l1["status"] == "approved_l1"

    l2 = approve(approver_l2_api, request_id)
    assert l2["status"] == "approved"

    # Evidencia de negocio: el recurso queda aplicado por merge, no reemplazado.
    resource = requester_api.get(f"/resources/{CUENTA_PRINCIPAL['id']}")
    assert resource.status_code == 200, resource.text
    body = resource.json()
    validate(body, "resource")
    assert body["values"] == {**CUENTA_PRINCIPAL["values"], "saldo": 999}
    assert body["values"]["moneda"] == "EUR"
    assert body["values"]["estado"] == "abierta"


@pytest.mark.parametrize(
    ("levels", "emptying_approvers", "empty_levels"),
    [
        # 2 niveles activos: se intenta vaciar L1, L2 o ambos.
        (2, {"level_1": [], "level_2": [USER_IDS["approver_l2"]]}, ["nivel 1"]),
        (2, {"level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]], "level_2": []}, ["nivel 2"]),
        (2, {"level_1": [], "level_2": []}, ["nivel 1", "nivel 2"]),
        # 1 nivel activo: solo L1 es un nivel requerido.
        (1, {"level_1": [], "level_2": []}, ["nivel 1"]),
    ],
)
def test_put_flow_approvers_vaciar_con_flujo_activo_rechazado(admin_api, levels, emptying_approvers, empty_levels):
    """Con el flujo activo, vaciar un nivel requerido se rechaza sin persistir."""

    # H-06: vaciar un nivel con el flujo activo devuelve 200 y persiste (esperado 422)
    active_approvers = {
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]] if levels == 2 else [],
    }
    activate_flow(admin_api, levels=levels, approvers=active_approvers)

    # Acción bajo prueba: PUT directo que dejaría vacío un nivel requerido.
    resp = admin_api.put("/flow/approvers", json=approvers_config(emptying_approvers))

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list), detail
    assert all(isinstance(item, str) for item in detail), detail
    joined = " ".join(detail)
    for level in empty_levels:
        assert level in joined, detail

    # Evidencia de negocio: el rechazo no toca los aprobadores activos.
    unchanged = get_flow_approvers(admin_api)
    validate(unchanged, "flow_approvers")
    assert unchanged["level_1"] == active_approvers["level_1"]
    assert unchanged["level_2"] == active_approvers["level_2"]


def test_put_flow_approvers_reemplazo_valido_con_flujo_activo(admin_api):
    """Con el flujo activo se puede reemplazar por aprobadores válidos y no vacíos."""

    active_approvers = {
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    }
    activate_flow(admin_api, levels=2, approvers=active_approvers)

    # Acción bajo prueba: reemplazo por otros aprobadores, ambos niveles no vacíos.
    replacement = {
        "level_1": [USER_IDS["approver_l1"]],
        "level_2": [USER_IDS["approver_l1_dos"]],
    }
    resp = admin_api.put("/flow/approvers", json=approvers_config(replacement))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    validate(data, "flow_approvers")
    assert data["level_1"] == replacement["level_1"]
    assert data["level_2"] == replacement["level_2"]

    confirm = get_flow_approvers(admin_api)
    validate(confirm, "flow_approvers")
    assert confirm["level_1"] == replacement["level_1"]
    assert confirm["level_2"] == replacement["level_2"]


@pytest.mark.parametrize(
    ("levels", "approvers", "uncovered"),
    [
        # 2 niveles: el único aprobador de L1 es el usuario inactivo 10.
        (2, {"level_1": [USER_IDS["inactive"]], "level_2": [USER_IDS["approver_l2"]]}, ["nivel 1", str(USER_IDS["inactive"])]),
        # 2 niveles: el único aprobador de L2 es el usuario inactivo 10.
        (2, {"level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]], "level_2": [USER_IDS["inactive"]]}, ["nivel 2", str(USER_IDS["inactive"])]),
        # 1 nivel: el único aprobador de L1 es el usuario inactivo 10.
        (1, {"level_1": [USER_IDS["inactive"]], "level_2": []}, ["nivel 1", str(USER_IDS["inactive"])]),
    ],
)
def test_put_flow_config_activar_nivel_sin_aprobador_funcional_rechazado(admin_api, levels, approvers, uncovered):
    """No se puede activar un flujo con un nivel cuyo único aprobador es inactivo/inexistente."""

    # H-07: activar con un nivel cuyo único aprobador es inactivo/inexistente devuelve 200 (esperado 422)
    set_approvers(admin_api, approvers=approvers)

    # Acción bajo prueba: PUT directo que activa el flujo.
    resp = admin_api.put("/flow/config", json=flow_config(levels, active=True))

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list), detail
    assert all(isinstance(item, str) for item in detail), detail
    joined = " ".join(detail)
    assert any(marker in joined for marker in uncovered), detail

    # Evidencia de negocio: el rechazo no activa nada (el seed sigue inactivo).
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 2, "active": False}


def test_put_flow_config_activo_un_nivel_no_pasa_a_dos_sin_l2(admin_api):
    """Con el flujo de 1 nivel activo no se puede pasar a 2 niveles sin aprobadores L2."""

    activate_flow(admin_api, levels=1, approvers={
        "level_1": [USER_IDS["approver_l1"]],
        "level_2": [],
    })

    # Acción bajo prueba: intentar pasar a 2 niveles dejando L2 vacío.
    resp = admin_api.put("/flow/config", json=flow_config(levels=2, active=True))

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")
    assert data["detail"] == ["nivel 2 sin aprobadores"]

    # Evidencia de negocio: la configuración no cambia (sigue 1 nivel activo).
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 1, "active": True}


def test_put_flow_overrides_persiste_y_get_confirma(admin_api):
    """El admin define el override de un usuario y el GET devuelve exactamente lo mismo."""

    # Precondición: aprobadores del workspace, para comprobar que el override no los altera.
    set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    })

    # Acción bajo prueba: override del usuario 9.
    data = set_approvers_override(admin_api, USER_IDS["requester_override"], {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    })

    validate(data, "flow_overrides")
    assert data["user_id"] == USER_IDS["requester_override"]
    assert data["level_1"] == [USER_IDS["override_l1"]]
    assert data["level_2"] == [USER_IDS["override_l2"]]

    # Evidencia de negocio: el GET devuelve el mismo override.
    confirm = get_flow_overrides(admin_api, USER_IDS["requester_override"])

    validate(confirm, "flow_overrides")
    assert confirm["user_id"] == USER_IDS["requester_override"]
    assert confirm["level_1"] == [USER_IDS["override_l1"]]
    assert confirm["level_2"] == [USER_IDS["override_l2"]]

    # Evidencia de negocio: el override de 9 no toca al de otro usuario ni al workspace.
    other = get_flow_overrides(admin_api, USER_IDS["requester"])
    validate(other, "flow_overrides")
    assert other == {"user_id": USER_IDS["requester"], "level_1": [], "level_2": []}

    workspace = get_flow_approvers(admin_api)
    validate(workspace, "flow_approvers")
    assert workspace["level_1"] == [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]]
    assert workspace["level_2"] == [USER_IDS["approver_l2"]]


def test_put_flow_overrides_reemplaza_por_nivel(admin_api):
    """Reconfigurar el override reemplaza sus niveles, sin duplicar ids ni arrastrar los previos."""

    user_id = USER_IDS["requester_override"]
    set_approvers_override(admin_api, user_id, {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    })

    # Acción bajo prueba: L1 pasa a [7, 8] y L2 se vacía.
    data = set_approvers_override(admin_api, user_id, {
        "level_1": [USER_IDS["override_l1"], USER_IDS["override_l2"]],
        "level_2": [],
    })

    validate(data, "flow_overrides")
    assert data["level_1"] == [USER_IDS["override_l1"], USER_IDS["override_l2"]]
    assert data["level_2"] == []

    # Evidencia de negocio: no queda el 7 duplicado ni el 8 arrastrado en L2.
    confirm = get_flow_overrides(admin_api, user_id)
    validate(confirm, "flow_overrides")
    assert confirm["level_1"] == [USER_IDS["override_l1"], USER_IDS["override_l2"]]
    assert confirm["level_2"] == []


def test_get_flow_overrides_sin_override_devuelve_vacio(admin_api):
    """Sin override definido, el GET de un usuario devuelve listas vacías en ambos niveles."""

    data = get_flow_overrides(admin_api, USER_IDS["requester"])

    validate(data, "flow_overrides")
    assert data == {"user_id": USER_IDS["requester"], "level_1": [], "level_2": []}


def test_get_flow_overrides_usuario_inexistente_devuelve_vacio(admin_api):
    """La lectura de overrides no filtra por existencia: un usuario inexistente devuelve listas vacías."""

    data = get_flow_overrides(admin_api, 999)

    validate(data, "flow_overrides")
    assert data == {"user_id": 999, "level_1": [], "level_2": []}


@pytest.mark.parametrize("user_id", [999, USER_IDS["inactive"]])
def test_put_flow_overrides_usuario_invalido_422(admin_api, user_id):
    """Definir un override para un usuario inexistente o inactivo se rechaza sin persistir."""

    approvers = {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    }

    # Acción bajo prueba: PUT directo sobre un usuario inexistente o inactivo.
    resp = admin_api.put(f"/flow/overrides/{user_id}", json=approvers_config(approvers))

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")
    assert data["detail"] == [f"usuario {user_id} inexistente o inactivo"]

    # Evidencia de negocio: el rechazo no persiste ningún override.
    assert get_flow_overrides(admin_api, USER_IDS["requester_override"]) == {
        "user_id": USER_IDS["requester_override"], "level_1": [], "level_2": []
    }
    assert get_flow_overrides(admin_api, 999) == {"user_id": 999, "level_1": [], "level_2": []}


@pytest.mark.parametrize("approver_id", [USER_IDS["inactive"], 999])
def test_put_flow_overrides_aprobador_invalido_422(admin_api, approver_id):
    """Un nivel de override cuyo aprobador es inexistente o inactivo se rechaza sin persistir."""

    approvers = {"level_1": [approver_id], "level_2": []}

    # Acción bajo prueba: PUT directo con un aprobador inválido en L1.
    resp = admin_api.put(
        f"/flow/overrides/{USER_IDS['requester_override']}",
        json=approvers_config(approvers),
    )

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")
    assert data["detail"] == [f"aprobador {approver_id} inexistente o inactivo"]

    # Evidencia de negocio: el override del usuario 9 sigue vacío.
    assert get_flow_overrides(admin_api, USER_IDS["requester_override"]) == {
        "user_id": USER_IDS["requester_override"], "level_1": [], "level_2": []
    }


@pytest.mark.parametrize(
    ("token", "expected_status_code", "detail"),
    [
        (None, 401, None),
        (TOKENS["inactive"], 401, None),
        (TOKENS["requester"], 403, "Requiere administrador"),
        (TOKENS["approver_l1"], 403, "Requiere administrador"),
        (TOKENS["approver_l2"], 403, "Requiere administrador"),
        (TOKENS["admin"], 200, None),
    ],
)
def test_put_flow_overrides_roles(api, admin_api, token, expected_status_code, detail):
    """Solo el admin define overrides; el resto recibe 401/403 sin alterar el estado."""

    user_id = USER_IDS["requester_override"]
    approvers = {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    }

    # Acción bajo prueba: PUT directo con el cliente del rol parametrizado.
    resp = api(token).put(f"/flow/overrides/{user_id}", json=approvers_config(approvers))

    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()

    if expected_status_code == 200:
        validate(data, "flow_overrides")
        assert data["user_id"] == user_id
        assert data["level_1"] == [USER_IDS["override_l1"]]
        assert data["level_2"] == [USER_IDS["override_l2"]]

        confirm = get_flow_overrides(admin_api, user_id)
        validate(confirm, "flow_overrides")
        assert confirm["level_1"] == [USER_IDS["override_l1"]]
        assert confirm["level_2"] == [USER_IDS["override_l2"]]
    else:
        validate(data, "error")
        if detail is not None:
            assert data["detail"] == detail

        # Evidencia de negocio: el rechazo no define el override.
        unchanged = get_flow_overrides(admin_api, user_id)
        validate(unchanged, "flow_overrides")
        assert unchanged["level_1"] == []
        assert unchanged["level_2"] == []


@pytest.mark.inbox
@pytest.mark.request
def test_override_total_pisa_aprobadores_ws(admin_api, api):
    """El override del solicitante pisa a los aprobadores del workspace: solo los suyos ven la solicitud."""

    workspace = {
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    }
    set_approvers(admin_api, approvers=workspace)
    set_approvers_override(admin_api, USER_IDS["requester_override"], {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    })
    activate_flow(admin_api, levels=2, approvers=workspace)

    # Precondición: solicitud creada por el usuario con override.
    requester = api(TOKENS["requester_override"])
    created = create_request(
        requester,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Evidencia de negocio: el L1 asignado es el override (7), no el workspace (4 y 5).
    assert request_id in received_ids(api(TOKENS["override_l1"]))
    assert request_id not in received_ids(api(TOKENS["approver_l1"]))
    assert request_id not in received_ids(api(TOKENS["approver_l1_dos"]))
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))

    l1 = approve(api(TOKENS["override_l1"]), request_id)
    assert l1["status"] == "approved_l1"

    # Evidencia de negocio: el L2 asignado es el override (8), no el workspace (6).
    assert request_id in received_ids(api(TOKENS["override_l2"]))
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))

    # Evidencia de negocio: el solicitante la ve en enviadas.
    assert request_id in sent_ids(requester)


@pytest.mark.inbox
@pytest.mark.request
def test_override_solo_l2_mantiene_l1_ws(admin_api, api):
    """Un override que solo define L2 deja el L1 en manos de los aprobadores del workspace."""

    workspace = {
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    }
    set_approvers(admin_api, approvers=workspace)
    set_approvers_override(admin_api, USER_IDS["requester_2"], {
        "level_1": [],
        "level_2": [USER_IDS["override_l2"]],
    })
    activate_flow(admin_api, levels=2, approvers=workspace)

    # Precondición: solicitud creada por el usuario con override solo de L2.
    requester = api(TOKENS["requester_2"])
    created = create_request(
        requester,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes={"saldo": 999},
    )
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Evidencia de negocio: el L1 sigue asignado a los aprobadores del workspace (4 y 5).
    assert request_id in received_ids(api(TOKENS["approver_l1"]))
    assert request_id in received_ids(api(TOKENS["approver_l1_dos"]))
    assert request_id not in received_ids(api(TOKENS["override_l1"]))

    l1 = approve(api(TOKENS["approver_l1"]), request_id)
    assert l1["status"] == "approved_l1"

    # Evidencia de negocio: el L2 lo resuelve solo el override (8), no el workspace (6).
    assert request_id in received_ids(api(TOKENS["override_l2"]))
    assert request_id not in received_ids(api(TOKENS["approver_l2"]))


_FLOW_GET_ENDPOINTS = [
    ("/flow/config", "flow_config"),
    ("/flow/approvers", "flow_approvers"),
    ("/flow/overrides/2", "flow_overrides"),
]


@pytest.mark.parametrize("token", [None, "token-inexistente", TOKENS["inactive"]])
@pytest.mark.parametrize("endpoint,_schema", _FLOW_GET_ENDPOINTS)
def test_get_flow_sin_token_desconocido_o_inactivo_401(api, endpoint, _schema, token):
    """Sin token, con token desconocido o con el usuario inactivo, los GET de /flow responden 401."""

    # Acción bajo prueba: GET directo con la credencial inválida parametrizada.
    resp = api(token).get(endpoint)

    assert resp.status_code == 401, resp.text
    data = resp.json()
    validate(data, "error")
    assert data["detail"]


@pytest.mark.parametrize("endpoint,schema", _FLOW_GET_ENDPOINTS)
def test_get_flow_cualquier_autenticado_200(api, endpoint, schema):
    """Cualquier usuario autenticado (no admin) puede leer los GET de /flow."""

    # Acción bajo prueba: GET con el token del solicitante (no admin).
    resp = api(TOKENS["requester"]).get(endpoint)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    validate(data, schema)

    if endpoint == "/flow/config":
        assert isinstance(data["active"], bool)
        assert data["levels"] in (1, 2)
    elif endpoint == "/flow/approvers":
        assert isinstance(data["level_1"], list)
        assert isinstance(data["level_2"], list)
    else:
        assert data["user_id"] == USER_IDS["requester"]


@pytest.mark.parametrize(
    ("level_1", "culprit"),
    [
        # H-01: id 999 (inexistente) en L1 devuelve 500 (esperado 422)
        ([999], "999"),
        # H-01: id 0 (inexistente) en L1 devuelve 500 (esperado 422)
        ([0], "0"),
        # H-01: id -1 (inexistente) en L1 devuelve 500 (esperado 422)
        ([-1], "-1"),
        # H-02: aprobador inactivo 10 en L1 devuelve 200 y persiste (esperado 422)
        ([USER_IDS["inactive"]], str(USER_IDS["inactive"])),
        # H-03: aprobador duplicado [4,4] en L1 devuelve 200 y persiste (esperado 422)
        ([USER_IDS["approver_l1"], USER_IDS["approver_l1"]], str(USER_IDS["approver_l1"])),
    ],
)
def test_put_flow_approvers_ids_invalidos_o_duplicados_rechazado(admin_api, level_1, culprit):
    """Un id inexistente, inactivo o duplicado en un nivel se rechaza sin persistir."""

    # Acción bajo prueba: L2 válido y L1 con el id inválido parametrizado.
    resp = admin_api.put(
        "/flow/approvers",
        json=approvers_config({
            "level_1": level_1,
            "level_2": [USER_IDS["approver_l2"]],
        }),
    )

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list), detail
    assert all(isinstance(item, str) for item in detail), detail
    assert any(culprit in item for item in detail), detail

    # Evidencia de negocio: la configuración inválida no se persiste.
    unchanged = get_flow_approvers(admin_api)
    validate(unchanged, "flow_approvers")
    assert unchanged["level_1"] == []
    assert unchanged["level_2"] == []


def test_put_flow_approvers_solape_l1_l2_rechazado(admin_api):
    """El mismo usuario no puede ser aprobador de L1 y L2 a la vez: se rechaza sin persistir."""

    # H-04: el mismo usuario en L1 y L2 devuelve 200 (esperado 422)
    approver = USER_IDS["approver_l1"]

    # Acción bajo prueba: el mismo id en ambos niveles.
    resp = admin_api.put(
        "/flow/approvers",
        json=approvers_config({"level_1": [approver], "level_2": [approver]}),
    )

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list), detail
    assert all(isinstance(item, str) for item in detail), detail
    joined = " ".join(detail)
    assert str(approver) in joined or "nivel" in joined, detail

    # Evidencia de negocio: el rechazo no persiste el solape.
    unchanged = get_flow_approvers(admin_api)
    validate(unchanged, "flow_approvers")
    assert unchanged["level_1"] == []
    assert unchanged["level_2"] == []


@pytest.mark.parametrize(
    ("level_1", "level_2"),
    [
        # H-05: override con el id 7 duplicado en L1 devuelve 200 y persiste (esperado 422)
        ([USER_IDS["override_l1"], USER_IDS["override_l1"]], []),
        # H-05: override con el id 7 en L1 y L2 (solape) devuelve 200 y persiste (esperado 422)
        ([USER_IDS["override_l1"]], [USER_IDS["override_l1"]]),
    ],
)
def test_put_flow_overrides_duplicados_y_solape_rechazado(admin_api, level_1, level_2):
    """Duplicados o el mismo aprobador en L1 y L2 de un override se rechazan sin persistir."""

    user_id = USER_IDS["requester_override"]

    # Acción bajo prueba: override con listas duplicadas o solapadas.
    resp = admin_api.put(
        f"/flow/overrides/{user_id}",
        json=approvers_config({"level_1": level_1, "level_2": level_2}),
    )

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list), detail
    assert all(isinstance(item, str) for item in detail), detail
    assert any(str(USER_IDS["override_l1"]) in item for item in detail), detail

    # Evidencia de negocio: el rechazo no persiste el override.
    unchanged = get_flow_overrides(admin_api, user_id)
    validate(unchanged, "flow_overrides")
    assert unchanged["level_1"] == []
    assert unchanged["level_2"] == []


@pytest.mark.parametrize(
    ("case", "path", "body"),
    [
        ("approvers", "/flow/approvers", {
            "level_1": [USER_IDS["approver_l1"], "5"],
            "level_2": [USER_IDS["approver_l2"]],
        }),
        ("overrides", f"/flow/overrides/{USER_IDS['requester_override']}", {
            "level_1": ["7"],
            "level_2": [USER_IDS["override_l2"]],
        }),
        ("config", "/flow/config", {"levels": 2, "active": "true"}),
    ],
)
def test_put_flow_coercion_de_tipos_rechazada(admin_api, case, path, body):
    """El contrato declara integer/boolean: un string no debe coercerse silenciosamente ni aplicarse."""

    # H-09: el contrato declara integer/boolean pero la API coerciona "5"/"7"/"true" y aplica (esperado 422)
    if case == "config":
        # Precondición: aprobadores válidos para que el rechazo sea por tipo y no por negocio.
        set_approvers(admin_api, approvers={
            "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
            "level_2": [USER_IDS["approver_l2"]],
        })

    # Acción bajo prueba: body con string en un campo declarado integer/boolean.
    resp = admin_api.put(path, json=body)

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    # Evidencia de negocio: la coerción no llega a aplicarse.
    if case == "approvers":
        unchanged = get_flow_approvers(admin_api)
        validate(unchanged, "flow_approvers")
        assert unchanged["level_1"] == []
        assert unchanged["level_2"] == []
    elif case == "overrides":
        unchanged = get_flow_overrides(admin_api, USER_IDS["requester_override"])
        validate(unchanged, "flow_overrides")
        assert unchanged["level_1"] == []
        assert unchanged["level_2"] == []
    else:
        unchanged = get_flow_config(admin_api)
        validate(unchanged, "flow_config")
        assert unchanged == {"levels": 2, "active": False}


@pytest.mark.parametrize(
    ("invalid_approvers", "markers"),
    [
        # H-08: reconfigurar el flujo activo dejando L1 con el inactivo 10 devuelve 200 y persiste (esperado 422)
        (
            {"level_1": [USER_IDS["inactive"]], "level_2": [USER_IDS["approver_l2"]]},
            ["nivel 1", str(USER_IDS["inactive"])],
        ),
        # H-08: reconfigurar el flujo activo dejando L2 con el inactivo 10 devuelve 200 y persiste (esperado 422)
        (
            {"level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]], "level_2": [USER_IDS["inactive"]]},
            ["nivel 2", str(USER_IDS["inactive"])],
        ),
        # H-08: reconfigurar el flujo activo con L1 mixto [4,10] devuelve 200 y persiste (esperado 422)
        (
            {"level_1": [USER_IDS["approver_l1"], USER_IDS["inactive"]], "level_2": [USER_IDS["approver_l2"]]},
            ["nivel 1", str(USER_IDS["inactive"])],
        ),
        # H-08: reconfigurar el flujo activo con el inexistente 999 en L1 devuelve 500 (esperado 422)
        (
            {"level_1": [999], "level_2": [USER_IDS["approver_l2"]]},
            ["nivel 1", "999"],
        ),
        # H-08: reconfigurar el flujo activo con L1 duplicado [4,4] devuelve 200 y persiste (esperado 422)
        (
            {"level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1"]], "level_2": [USER_IDS["approver_l2"]]},
            [str(USER_IDS["approver_l1"])],
        ),
        # H-08: reconfigurar el flujo activo con el mismo 4 en L1 y L2 devuelve 200 y persiste (esperado 422)
        (
            {"level_1": [USER_IDS["approver_l1"]], "level_2": [USER_IDS["approver_l1"]]},
            ["nivel", str(USER_IDS["approver_l1"])],
        ),
    ],
)
def test_put_flow_approvers_invalido_con_flujo_activo_rechazado(admin_api, invalid_approvers, markers):
    """Con el flujo activo, reconfigurar por listas inválidas o no funcionales se rechaza sin persistir."""

    active_approvers = {
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    }
    activate_flow(admin_api, levels=2, approvers=active_approvers)

    # Acción bajo prueba: PUT directo que reconfiguraría el flujo activo por una lista inválida.
    resp = admin_api.put("/flow/approvers", json=approvers_config(invalid_approvers))

    assert resp.status_code == 422, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list), detail
    assert all(isinstance(item, str) for item in detail), detail
    joined = " ".join(detail)
    assert any(marker in joined for marker in markers), detail

    # Evidencia de negocio: el rechazo deja intacto el flujo activo.
    approvers = get_flow_approvers(admin_api)
    validate(approvers, "flow_approvers")
    assert approvers["level_1"] == active_approvers["level_1"]
    assert approvers["level_2"] == active_approvers["level_2"]

    config = get_flow_config(admin_api)
    validate(config, "flow_config")
    assert config == {"levels": 2, "active": True}


@pytest.mark.parametrize(
    ("body", "expected_status_code", "expected_level_1", "expected_level_2"),
    [
        # Claves ausentes sin `required` en el contrato: usan el default [].
        ({}, 200, [], []),
        ({"level_1": [USER_IDS["approver_l1"]]}, 200, [USER_IDS["approver_l1"]], []),
        # Un nivel null no es una lista válida.
        ({"level_1": None, "level_2": [USER_IDS["approver_l2"]]}, 422, None, None),
        # Un nivel string tampoco es la lista declarada por el contrato.
        ({"level_1": "4", "level_2": [USER_IDS["approver_l2"]]}, 422, None, None),
        # Campo extra tolerado: se aplica solo lo declarado.
        (
            {"level_1": [USER_IDS["approver_l1"]], "level_2": [USER_IDS["approver_l2"]], "extra": 1},
            200,
            [USER_IDS["approver_l1"]],
            [USER_IDS["approver_l2"]],
        ),
    ],
)
def test_put_flow_approvers_cuerpo_malformado_rechazado(
    admin_api, body, expected_status_code, expected_level_1, expected_level_2
):
    """Faltar claves usa su default; null o tipo erróneo en un nivel se rechaza; los extras se ignoran."""

    # Acción bajo prueba: PUT directo con el body crudo parametrizado.
    resp = admin_api.put("/flow/approvers", json=body)

    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()

    if expected_status_code == 200:
        validate(data, "flow_approvers")
        assert data["level_1"] == expected_level_1
        assert data["level_2"] == expected_level_2
    else:
        validate(data, "error")

        # Error de validación de FastAPI: `detail` es lista de dicts, no de strings.
        detail = data["detail"]
        assert isinstance(detail, list) and detail, detail
        assert all(isinstance(item, dict) for item in detail), detail

    # Evidencia de negocio: el GET confirma lo aplicado o conserva el estado previo (seed vacío).
    confirm = get_flow_approvers(admin_api)
    validate(confirm, "flow_approvers")
    if expected_status_code == 200:
        assert confirm["level_1"] == expected_level_1
        assert confirm["level_2"] == expected_level_2
    else:
        assert confirm["level_1"] == []
        assert confirm["level_2"] == []


@pytest.mark.parametrize(
    ("body", "expected_status_code"),
    [
        # Falta `levels`: error de contrato.
        ({"active": True}, 422),
        # Falta `active`: error de contrato.
        ({"levels": 2}, 422),
        # `levels` null no es 1 ni 2.
        ({"levels": None, "active": True}, 422),
        # `levels` como string no es el integer declarado.
        ({"levels": "2", "active": True}, 422),
        # Campo extra tolerado: se aplica lo declarado.
        ({"levels": 2, "active": False, "extra": 1}, 200),
    ],
)
def test_put_flow_config_cuerpo_malformado_rechazado(admin_api, body, expected_status_code):
    """Faltar o mal tipar `levels`/`active` se rechaza como contrato; los extras no rompen nada."""

    # Acción bajo prueba: PUT directo con el body crudo parametrizado.
    resp = admin_api.put("/flow/config", json=body)

    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()

    if expected_status_code == 200:
        validate(data, "flow_config")
        assert data == {"levels": 2, "active": False}
    else:
        validate(data, "error")

        # Error de validación de FastAPI: `detail` es lista de dicts, no de strings.
        detail = data["detail"]
        assert isinstance(detail, list) and detail, detail
        assert all(isinstance(item, dict) for item in detail), detail

    # Evidencia de negocio: la configuración sigue siendo la del seed.
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 2, "active": False}


_OVERRIDE_USER_PATH = f"/flow/overrides/{USER_IDS['requester_override']}"


@pytest.mark.parametrize(
    ("method", "path", "body", "expected_status_code", "expected_level_1", "expected_level_2"),
    [
        # Claves ausentes sin `required` en el contrato: usan el default [].
        ("put", _OVERRIDE_USER_PATH, {}, 200, [], []),
        ("put", _OVERRIDE_USER_PATH, {"level_2": []}, 200, [], []),
        # Un nivel null no es una lista válida.
        ("put", _OVERRIDE_USER_PATH, {"level_1": None, "level_2": [USER_IDS["override_l2"]]}, 422, None, None),
        # Un nivel string tampoco es la lista declarada por el contrato.
        ("put", _OVERRIDE_USER_PATH, {"level_1": "7", "level_2": [USER_IDS["override_l2"]]}, 422, None, None),
        # Campo extra tolerado: se aplica solo lo declarado.
        (
            "put",
            _OVERRIDE_USER_PATH,
            {"level_1": [USER_IDS["override_l1"]], "level_2": [USER_IDS["override_l2"]], "extra": 1},
            200,
            [USER_IDS["override_l1"]],
            [USER_IDS["override_l2"]],
        ),
        # Path no entero: `int_parsing`.
        ("put", "/flow/overrides/abc", {"level_1": [USER_IDS["override_l1"]], "level_2": []}, 422, None, None),
        ("get", "/flow/overrides/abc", None, 422, None, None),
    ],
)
def test_put_flow_overrides_cuerpo_o_path_malformado_rechazado(
    admin_api, method, path, body, expected_status_code, expected_level_1, expected_level_2
):
    """Claves ausentes usan default; null/tipo erróneo y path no entero se rechazan con detalle de validación."""

    # Acción bajo prueba: llamada cruda según el método parametrizado.
    if method == "put":
        resp = admin_api.put(path, json=body)
    else:
        resp = admin_api.get(path)

    assert resp.status_code == expected_status_code, resp.text
    data = resp.json()

    if expected_status_code == 200:
        validate(data, "flow_overrides")
        assert data["user_id"] == USER_IDS["requester_override"]
        assert data["level_1"] == expected_level_1
        assert data["level_2"] == expected_level_2
    else:
        validate(data, "error")

        # Error de validación de FastAPI: `detail` es lista de dicts, no de strings.
        detail = data["detail"]
        assert isinstance(detail, list) and detail, detail
        assert all(isinstance(item, dict) for item in detail), detail

    # Evidencia de negocio: el override del usuario 9 refleja lo aplicado o se conserva vacío.
    confirm = get_flow_overrides(admin_api, USER_IDS["requester_override"])
    validate(confirm, "flow_overrides")
    if expected_status_code == 200:
        assert confirm["level_1"] == expected_level_1
        assert confirm["level_2"] == expected_level_2
    else:
        assert confirm["level_1"] == []
        assert confirm["level_2"] == []


@pytest.mark.parametrize(
    ("user_id", "body", "expected_detail"),
    [
        # Path fuera de rango: el usuario no existe.
        (0, {"level_1": [USER_IDS["override_l1"]], "level_2": []}, ["usuario 0 inexistente o inactivo"]),
        (-1, {"level_1": [USER_IDS["override_l1"]], "level_2": []}, ["usuario -1 inexistente o inactivo"]),
        # Aprobador 0 inexistente.
        (9, {"level_1": [0], "level_2": []}, ["aprobador 0 inexistente o inactivo"]),
        # Listas mixtas con un id inexistente o inactivo.
        (
            9,
            {"level_1": [USER_IDS["override_l1"], 999], "level_2": []},
            [f"aprobador 999 inexistente o inactivo"],
        ),
        (
            9,
            {"level_1": [USER_IDS["override_l1"], USER_IDS["inactive"]], "level_2": []},
            [f"aprobador {USER_IDS['inactive']} inexistente o inactivo"],
        ),
        (
            9,
            {"level_1": [], "level_2": [USER_IDS["override_l2"], USER_IDS["inactive"]]},
            [f"aprobador {USER_IDS['inactive']} inexistente o inactivo"],
        ),
        # Camino válido: los rechazos anteriores no lo bloquean.
        (9, {"level_1": [USER_IDS["override_l1"]], "level_2": [USER_IDS["override_l2"]]}, None),
    ],
)
def test_put_flow_overrides_ids_fuera_de_rango_o_mixtos_rechazado(admin_api, user_id, body, expected_detail):
    """Un usuario o aprobador fuera de rango, o mezclado con válidos, se rechaza sin persistir."""

    # Acción bajo prueba: PUT directo con el path/body parametrizado.
    resp = admin_api.put(f"/flow/overrides/{user_id}", json=body)

    if expected_detail is None:
        assert resp.status_code == 200, resp.text
        data = resp.json()
        validate(data, "flow_overrides")
        assert data["user_id"] == user_id
        assert data["level_1"] == body["level_1"]
        assert data["level_2"] == body["level_2"]
    else:
        assert resp.status_code == 422, resp.text
        data = resp.json()
        validate(data, "error")
        assert data["detail"] == expected_detail

    # Evidencia de negocio: el rechazo no deja override para el usuario 9.
    unchanged = get_flow_overrides(admin_api, USER_IDS["requester_override"])
    validate(unchanged, "flow_overrides")
    if expected_detail is None:
        assert unchanged["level_1"] == body["level_1"]
        assert unchanged["level_2"] == body["level_2"]
    else:
        assert unchanged["level_1"] == []
        assert unchanged["level_2"] == []


def test_put_flow_approvers_mismo_body_dos_veces_no_duplica(admin_api):
    """Aplicar el mismo PUT de aprobadores dos veces es idempotente: el GET queda exacto, sin duplicar."""

    approvers = {
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    }

    # Acción bajo prueba: la misma configuración aplicada dos veces.
    first = admin_api.put("/flow/approvers", json=approvers_config(approvers))
    assert first.status_code == 200, first.text
    validate(first.json(), "flow_approvers")

    second = admin_api.put("/flow/approvers", json=approvers_config(approvers))
    assert second.status_code == 200, second.text
    validate(second.json(), "flow_approvers")

    # Evidencia de negocio: el estado final es exacto, sin elementos ni repeticiones añadidas.
    confirm = get_flow_approvers(admin_api)
    validate(confirm, "flow_approvers")
    assert confirm["level_1"] == [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]]
    assert confirm["level_2"] == [USER_IDS["approver_l2"]]


def test_put_flow_config_misma_config_dos_veces_es_idempotente(admin_api):
    """Aplicar la misma configuración de flujo dos veces no deja estado intermedio ni falla la segunda vez."""

    set_approvers(admin_api, approvers={
        "level_1": [USER_IDS["approver_l1"], USER_IDS["approver_l1_dos"]],
        "level_2": [USER_IDS["approver_l2"]],
    })

    # Acción bajo prueba: la misma configuración aplicada dos veces.
    first = admin_api.put("/flow/config", json=flow_config(levels=2, active=True))
    assert first.status_code == 200, first.text
    validate(first.json(), "flow_config")

    second = admin_api.put("/flow/config", json=flow_config(levels=2, active=True))
    assert second.status_code == 200, second.text
    validate(second.json(), "flow_config")

    # Evidencia de negocio: el GET final es la configuración activa de 2 niveles.
    confirm = get_flow_config(admin_api)
    validate(confirm, "flow_config")
    assert confirm == {"levels": 2, "active": True}


def test_put_flow_overrides_mismo_body_dos_veces_no_duplica(admin_api):
    """Aplicar el mismo PUT de override dos veces no duplica ids ni contamina a otros usuarios."""

    user_id = USER_IDS["requester_override"]
    approvers = {
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    }

    # Acción bajo prueba: el mismo override aplicado dos veces.
    first = set_approvers_override(admin_api, user_id, approvers)
    validate(first, "flow_overrides")

    second = set_approvers_override(admin_api, user_id, approvers)
    validate(second, "flow_overrides")

    # Evidencia de negocio: el override queda exacto, sin el 7 duplicado ni el 8 repetido.
    confirm = get_flow_overrides(admin_api, user_id)
    validate(confirm, "flow_overrides")
    assert confirm == {
        "user_id": user_id,
        "level_1": [USER_IDS["override_l1"]],
        "level_2": [USER_IDS["override_l2"]],
    }

    # Evidencia de negocio: el override de otro usuario sigue vacío.
    other = get_flow_overrides(admin_api, USER_IDS["requester"])
    validate(other, "flow_overrides")
    assert other == {"user_id": USER_IDS["requester"], "level_1": [], "level_2": []}
