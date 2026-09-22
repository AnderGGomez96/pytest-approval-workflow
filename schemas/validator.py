import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

_SCHEMAS_DIR = Path(__file__).parent
_VALIDATORS = {
    path.stem:Draft202012Validator(
        json.loads(path.read_text(encoding="utf-8")),
        format_checker=FormatChecker()
    )
    for path in _SCHEMAS_DIR.glob("*.json")
}


def validate(instance, schema_name: str)-> None:
    """Valida `instance` contra `schemas/<schema_name>.json`; falla con la ruta del campo"""
    _VALIDATORS[schema_name].validate(instance)