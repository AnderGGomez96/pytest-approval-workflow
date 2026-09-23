# pytest-approval-workflow

[![Regresión e2e approval-workflow](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/workflows/regresion.yml/badge.svg?branch=main)](https://github.com/AnderGGomez96/pytest-approval-workflow/actions/workflows/regresion.yml)

Suite de pruebas automatizadas black-box (pytest) para la API `approval-workflow`.
Este repositorio no contiene la API: solo el cliente HTTP, los datos de prueba,
los helpers, los esquemas de contrato y los casos de prueba que la consumen por HTTP.

## Estructura del proyecto

```text
pytest-approval-workflow/
├── client/               # Cliente HTTP (ApiClient sobre requests)
│   └── api_client.py
├── data/                 # Datos de prueba (tokens, payloads, recursos)
│   ├── tokens.py
│   ├── payloads.py
│   └── resources.py
├── helpers/              # Utilidades de preparación y acciones (health, flow, requests, inbox, resources)
│   ├── health.py
│   ├── flow.py
│   ├── request_flow.py
│   ├── inbox.py
│   └── resources.py
├── schemas/              # Contratos JSON Schema + validador
│   ├── *.json
│   └── validator.py
├── tests/                # Casos de prueba
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_flow_config.py
│   ├── test_approval_flow.py
│   ├── test_conciliar_inactive.py
│   ├── test_conciliar_active.py
│   ├── test_request_1level.py
│   ├── test_request_2levels.py
│   ├── test_request_self_approval.py
│   ├── test_request_cancel.py
│   ├── test_request_detail.py
│   ├── test_request_detail_visibility.py
│   ├── test_inbox_received.py
│   ├── test_inbox_sent.py
│   ├── test_reset.py
│   ├── test_identity.py
│   └── test_resources.py
├── conftest.py           # Fixtures globales (URL base, espera de /health, reset, clientes por rol)
├── pytest.ini            # Configuración de pytest
└── requirements.txt      # Dependencias (pytest, requests, jsonschema)
```

## Instalación

Requisitos: Python 3.13 y la API `approval-workflow` en ejecución.

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

1. Arranca la API bajo prueba (por defecto en `http://localhost:8000`).
2. Define la URL base si es distinta (opcional, también vía archivo `.env` no versionado):

```powershell
$env:APPROVAL_BASE_URL = "http://localhost:8000"
```

```bash
export APPROVAL_BASE_URL="http://localhost:8000"
```

3. Ejecuta la suite:

```bash
pytest          # toda la suite
pytest -m smoke # solo pruebas de disponibilidad mínima
pytest -q       # salida compacta
```
