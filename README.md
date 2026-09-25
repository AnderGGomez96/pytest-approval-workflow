# pytest-approval-workflow

[![Regresión e2e approval-workflow](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/workflows/regresion.yml/badge.svg?branch=main)](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/workflows/regresion.yml)

**pytest · requests · jsonschema — 238 casos black-box con integración continua en GitHub Actions.**

Suite de pruebas automatizadas black-box (pytest) para la API `approval-workflow`, réplica
sintética del flujo de aprobaciones de una plataforma de conciliación financiera (cliente
anonimizado). Este repositorio no contiene la API: solo el cliente HTTP, los datos de prueba,
los helpers, los esquemas de contrato y los casos que la consumen por HTTP.

Es la evidencia pública de la arquitectura y las decisiones de una suite real, reconstruida
sobre una API de prueba, sin código ni datos del cliente.

**Resultado medido (2026-09-23):** 238 casos · regresión 70/70 en ~1 minuto · 9 JSON Schema ·
seis ejecuciones de integración continua en verde.

## Arquitectura en cuatro capas

| Capa | Carpeta | Responsabilidad |
|---|---|---|
| 1. Datos de prueba | `data/` | única fuente de tokens, ids y payloads; sin lógica |
| 2. Helpers | `helpers/` | acciones de negocio reutilizables (configurar flujo, crear/resolver/cancelar solicitudes, bandejas, recursos) |
| 3. Request | `client/` | transporte HTTP puro (base_url, token, timeout); no conoce reglas de negocio |
| 4. JSON Schema | `schemas/` | contrato de respuestas + validador por nombre |

`tests/` no es una capa de infraestructura: orquesta helpers y afirma negocio. Regla de
dependencias: `tests/ → helpers/ → client/ → HTTP`; `data/` y `schemas/` son hojas.
Orden de aserciones: status → schema → semántica.

```text
pytest-approval-workflow/
├── client/       # capa 3: transporte HTTP (ApiClient sobre requests)
├── data/         # capa 1: tokens, payloads y recursos de prueba
├── helpers/      # capa 2: acciones de negocio (health, flow, request_flow, inbox, resources)
├── schemas/      # capa 4: 9 JSON Schema + validador
├── tests/        # 238 casos en 17 archivos (marcadores: smoke, regresion, flow, request, inbox, default)
├── conftest.py   # fixtures: base_url, espera de /health, reset y clientes por rol
├── pytest.ini    # marcadores y opciones
└── requirements.txt
```

## Datos de prueba y entornos

- Cada caso parte de estado limpio con `POST /test/reset` (determinista, sin dependencia de orden).
- El seed deja recursos y usuarios sintéticos; no hay datos reales, personales ni secretos.
- Instancia demo pública: `https://approbal-workflow.duckdns.org`. No es producción:
  `POST /test/reset` está abierto por diseño.
- `.env.example` apunta a esa instancia; también puedes apuntar a una API local.

## Integración continua

Workflow `Regresión e2e approval-workflow` (`.github/workflows/regresion.yml`):

- `repository_dispatch` (`approval-workflow-deployed`): corre el subconjunto `regresion` en cada despliegue de la API.
- `workflow_dispatch`: permite elegir `regresion` o `all`.
- `schedule`: nocturno `0 3 * * *` (primer disparo pendiente de verificación).
- `concurrency` serializa el acceso a la instancia viva; timeout de 30 minutos.
- Artefacto por ejecución: JUnit + reporte HTML (`report-<suite>`).

| Ejecución | Disparador | Suite | Resultado | Tiempo |
|---|---|---|---|---|
| [35874491733](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/runs/35874491733) | despliegue | `regresion` | 70 passed | 51,66 s |
| [35877828129](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/runs/35877828129) | manual | `all` | 25 failed, 213 passed (línea base previa a correcciones) | 227,63 s |
| [35879328887](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/runs/35879328887) | manual | `all` | 4 failed, 234 passed | 272,02 s |
| [35890500746](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/runs/35890500746) | despliegue | `regresion` | 70 passed | 54,60 s |
| [35891881873](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/runs/35891881873) | manual | `regresion` | 70 passed | 67,58 s |
| [35897240909](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/runs/35897240909) | manual | `all` | 4 failed, 234 passed | 82,35 s |

Todas las ejecuciones concluyen en verde: en la suite completa, los 4 rojos clasificados no
tumban el run (`continue-on-error`) y su detalle queda en el artefacto JUnit/HTML.

## Estabilidad y análisis de fallos

Decisiones heredadas de la suite original (cliente anonimizado):

- Sin política formal de cuarentena: cada fallo se reproducía, se descartaban hipótesis
  (permisos, variables de entorno, despliegue) y, si era reproducible, se documentaba y se
  escalaba a desarrollo.
- El paso de 20 fallos a cero tuvo causas mixtas: inestabilidad de la propia suite (fixtures
  que cacheaban su escritura y contaminación de datos entre casos) y defectos del producto o
  del ambiente (funcionalidad parcial, diseño irresoluble, cambios sin desplegar).
- En integración continua, un incidente recurrente fue el de feature flags no comunicadas:
  las pruebas fallaban hasta activar la bandera en el ambiente correspondiente.

## Cómo ejecutar en local

1. `git clone https://github.com/AnderGGomez96/pytest-approval-workflow.git`
2. Crea el entorno: `python -m venv .venv` y actívalo.
3. Instala dependencias: `pip install -r requirements.txt`
4. Define la URL base: copia `.env.example` a `.env` (o exporta `APPROVAL_BASE_URL`).
5. Ejecuta: `pytest` (toda) · `pytest -m smoke` (disponibilidad mínima) · `pytest -m regresion` (regresión).

Requisito: Python 3.13.

## Cómo verificar el flujo en verde

- Insignia de la cabecera: estado de la última ejecución sobre `main`.
- Historial y últimas ejecuciones:
  https://github.com/AnderGGomez96/pytest-approval-workflow/actions/workflows/regresion.yml

## Alcance y límites

- Réplica sintética: no incluye el código de la API bajo prueba (propietario), ni el contrato
  OpenAPI real, ni los 26 esquemas de la suite original (aquí se publican 9), ni datos o
  tokens reales.
- En construcción: 4 casos de la suite completa permanecen en rojo clasificados (reportados a
  desarrollo; no son regresiones) y el primer disparo nocturno está pendiente de verificación.
- Sin secretos: `.env` no se versiona y los tokens del seed son sintéticos.

## Licencia y contacto

MIT. Contacto: anderggomez96@gmail.com · [LinkedIn](https://www.linkedin.com/in/anderson-gomez-gomez/)
