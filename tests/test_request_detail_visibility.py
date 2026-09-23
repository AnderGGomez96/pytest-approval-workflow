import pytest

from data.resources import CUENTA_PRINCIPAL
from data.tokens import TOKENS
from helpers.flow import activate_flow
from helpers.request_flow import create_request, get_request_detail, get_request_log
from schemas.validator import validate

pytestmark = pytest.mark.request

_PROPUESTO = {"saldo": 999}

# Rutas de lectura del detalle y del log bajo prueba.
_LECTURAS = ("/requests/{request_id}", "/requests/{request_id}/log")


def _assert_error_de_negocio(resp, request_id):
    """Un 404 de negocio valida `error`, trae `detail` lista de strings y no filtra el contenido."""
    assert resp.status_code == 404, resp.text
    data = resp.json()
    validate(data, "error")

    detail = data["detail"]
    assert isinstance(detail, list) and detail, detail
    assert all(isinstance(item, str) for item in detail), detail
    assert str(request_id) in " ".join(detail), detail

    # El cuerpo del error no expone el contenido real de la solicitud.
    for clave in ("before", "proposed", "applied", "actor_name", "comment"):
        assert clave not in resp.text, resp.text


@pytest.mark.parametrize(
    ("actor", "token"),
    [
        ("tercero", TOKENS["requester_2"]),
        ("l2_en_pending", TOKENS["approver_l2"]),
        ("admin", TOKENS["admin"]),
    ],
)
def test_detalle_y_log_sin_visibilidad_404(admin_api, requester_api, api, actor, token):
    """Tercero (3), L2 (6) en pending y admin no tienen visibilidad: 404 en detalle y log,
    con error de negocio y sin filtrar el contenido (S-26, AC-8.3)."""

    # Precondición: flujo 2 niveles activo; la solicitud pending solo es visible a L1 y al solicitante.
    activate_flow(admin_api, levels=2)

    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes=dict(_PROPUESTO),
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0

    # Borde: el solicitante sí ve detalle y log (200), así el 404 no se debe a un id inexistente.
    detalle = get_request_detail(requester_api, request_id)
    validate(detalle, "request_detail")
    assert detalle["before"] == CUENTA_PRINCIPAL["values"]
    assert detalle["proposed"] == _PROPUESTO
    assert detalle["applied"] == CUENTA_PRINCIPAL["values"]

    log = get_request_log(requester_api, request_id)
    assert len(log) == 1, log
    validate(log[0], "request_log_entry")
    assert log[0]["action"] == "create"
    assert log[0]["from_status"] is None
    assert log[0]["to_status"] == "pending"

    # Acción bajo prueba: el actor sin visibilidad no puede leer detalle ni log.
    cliente = api(token)
    for ruta in _LECTURAS:
        resp = cliente.get(ruta.format(request_id=request_id))
        _assert_error_de_negocio(resp, request_id)


def test_404_sin_visibilidad_indistinguible_de_inexistente(admin_api, requester_api, api):
    """H-10: el 404 distingue "no visible" de "inexistente" (esperado 404 indistinguible).

    N-19 (handoff F-10): con una solicitud real `pending` sin visibilidad para el tercero 3, el
    `404` de detalle y log debe ser indistinguible del de un id inexistente (`999`): mismo status
    y mismo `detail`. La API actual filtra la existencia diferenciando los mensajes.
    """

    # Borde: existe una solicitud real `pending`; el 404 del tercero no se debe a un id inexistente.
    activate_flow(admin_api, levels=2)
    created = create_request(
        requester_api,
        resource_id=CUENTA_PRINCIPAL["id"],
        changes=dict(_PROPUESTO),
    )
    validate(created, "request")
    assert created["status"] == "pending"
    request_id = created["id"]
    assert isinstance(request_id, int) and request_id > 0
    assert get_request_detail(requester_api, request_id)["proposed"] == _PROPUESTO

    # Acción bajo prueba: mismo tercero lee la solicitud sin visibilidad y un id inexistente.
    cliente = api(TOKENS["requester_2"])
    for ruta in _LECTURAS:
        sin_visibilidad = cliente.get(ruta.format(request_id=request_id))
        inexistente = cliente.get(ruta.format(request_id=999))

        assert sin_visibilidad.status_code == 404, sin_visibilidad.text
        assert inexistente.status_code == 404, inexistente.text
        validate(sin_visibilidad.json(), "error")
        validate(inexistente.json(), "error")

        # Indistinguibles: mismo `detail` para la solicitud no visible y la inexistente.
        assert sin_visibilidad.json()["detail"] == inexistente.json()["detail"], (
            "# H-10: el 404 distingue 'no visible' de 'inexistente' (esperado 404 indistinguible): "
            f"{sin_visibilidad.json()['detail']!r} != {inexistente.json()['detail']!r}"
        )


@pytest.mark.parametrize(
    ("request_id", "expected_status", "detail_format"),
    [
        (999, 404, "strings"),
        (0, 404, "strings"),
        (-1, 404, "strings"),
        ("abc", 422, "dicts"),
    ],
)
def test_detalle_y_log_id_invalido(
    admin_api, requester_api, request_id, expected_status, detail_format
):
    """Un id inexistente da 404 de negocio y un path no entero 422 de validación, con el mismo
    formato en detalle y log y nunca 500 (N-10/N-11)."""

    # Borde: existe una solicitud real que el solicitante lee con 200; el 404/422 no se debe a un
    # id inexistente ni a falta de visibilidad.
    activate_flow(admin_api, levels=2)
    created = create_request(requester_api, resource_id=CUENTA_PRINCIPAL["id"], changes=dict(_PROPUESTO))
    validate(created, "request")
    assert created["status"] == "pending"
    real_id = created["id"]
    assert isinstance(real_id, int) and real_id > 0
    assert get_request_detail(requester_api, real_id)["proposed"] == _PROPUESTO

    # Acción bajo prueba: lectura directa con el path inválido parametrizado, en ambas rutas.
    for ruta in _LECTURAS:
        resp = admin_api.get(ruta.format(request_id=request_id))

        assert resp.status_code == expected_status, resp.text
        data = resp.json()
        validate(data, "error")

        detail = data["detail"]
        assert isinstance(detail, list) and detail, detail

        if detail_format == "strings":
            # Error de negocio: lista de strings que menciona la solicitud pedida.
            assert all(isinstance(item, str) for item in detail), detail
            assert str(request_id) in " ".join(detail), detail
        else:
            # Error de validación de FastAPI: lista de dicts (`int_parsing`).
            assert all(isinstance(item, dict) for item in detail), detail
            assert any(item.get("type") == "int_parsing" for item in detail), detail
