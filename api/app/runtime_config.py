"""Project-scoped runtime configuration. Never expose secret values."""

from __future__ import annotations

import os
from typing import Any

from .db import load_optional_dotenv

GA_AZURE_CU_API_VERSION = "2025-11-01"
DEFAULT_AZURE_ANALYZER_ID = "prebuilt-document"


def _nonempty(name: str) -> bool:
    value = os.environ.get(name)
    return bool(value) and bool(str(value).strip())


def _first_present(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and str(value).strip():
            return str(value).strip()
    return None


def snapshot() -> dict[str, Any]:
    """Boolean/presence snapshot for UI and logs. No secret material."""
    load_optional_dotenv()
    model_name = _nonempty("LUCID_MODEL_NAME")
    model_base = _nonempty("LUCID_MODEL_BASE_URL")
    model_key = _nonempty("LUCID_MODEL_API_KEY")
    azure_endpoint = _nonempty("AZURE_CONTENT_UNDERSTANDING_ENDPOINT") or _nonempty(
        "LUCID_AZURE_CU_ENDPOINT"
    )
    azure_key = (
        _nonempty("AZURE_CONTENT_UNDERSTANDING_KEY")
        or _nonempty("AZURE_CONTENT_UNDERSTANDING_API_KEY")
        or _nonempty("LUCID_AZURE_CU_KEY")
    )
    azure_analyzer = _nonempty("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID") or _nonempty(
        "LUCID_AZURE_CU_ANALYZER_ID"
    )
    model_configured = model_name and model_key and model_base
    azure_configured = azure_endpoint and azure_key
    return {
        "model": {
            "name_present": model_name,
            "base_url_present": model_base,
            "api_key_present": model_key,
            "api_version_present": _nonempty("LUCID_MODEL_API_VERSION"),
            "configured": bool(model_configured),
        },
        "azure_content_understanding": {
            "endpoint_present": bool(azure_endpoint),
            "key_present": bool(azure_key),
            "analyzer_id_present": bool(azure_analyzer),
            "analyzer_id_default": DEFAULT_AZURE_ANALYZER_ID,
            "api_version": os.environ.get("AZURE_CONTENT_UNDERSTANDING_API_VERSION", "").strip()
            or GA_AZURE_CU_API_VERSION,
            "configured": bool(azure_configured),
        },
        "live_agent_possible": bool(model_configured),
        "live_azure_possible": bool(azure_configured),
        "solver": "deterministic_training_schedule",
        "setup": {
            "env_file": "lucid/.env (copy from .env.example)",
            "model_keys": [
                "LUCID_MODEL_NAME",
                "LUCID_MODEL_BASE_URL",
                "LUCID_MODEL_API_KEY",
            ],
            "optional_model_keys": ["LUCID_MODEL_API_VERSION", "LUCID_MODEL_TIMEOUT_SECONDS"],
            "azure_keys": [
                "AZURE_CONTENT_UNDERSTANDING_ENDPOINT",
                "AZURE_CONTENT_UNDERSTANDING_KEY",
            ],
            "optional_azure_keys": [
                "AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID",
                "AZURE_CONTENT_UNDERSTANDING_API_VERSION",
            ],
        },
    }


def model_settings() -> dict[str, str | None]:
    load_optional_dotenv()
    return {
        "name": _first_present("LUCID_MODEL_NAME"),
        "base_url": _first_present("LUCID_MODEL_BASE_URL"),
        "api_key": _first_present("LUCID_MODEL_API_KEY"),
        "api_version": _first_present("LUCID_MODEL_API_VERSION"),
        "timeout": _first_present("LUCID_MODEL_TIMEOUT_SECONDS"),
    }


def azure_settings() -> dict[str, str | None]:
    load_optional_dotenv()
    return {
        "endpoint": _first_present(
            "AZURE_CONTENT_UNDERSTANDING_ENDPOINT", "LUCID_AZURE_CU_ENDPOINT"
        ),
        "key": _first_present(
            "AZURE_CONTENT_UNDERSTANDING_KEY",
            "AZURE_CONTENT_UNDERSTANDING_API_KEY",
            "LUCID_AZURE_CU_KEY",
        ),
        "analyzer_id": _first_present(
            "AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID", "LUCID_AZURE_CU_ANALYZER_ID"
        )
        or DEFAULT_AZURE_ANALYZER_ID,
        "api_version": _first_present("AZURE_CONTENT_UNDERSTANDING_API_VERSION")
        or GA_AZURE_CU_API_VERSION,
    }
