"""One Azure Content Understanding client. GA API 2025-11-01. No provider router.

Operation IDs come from the installed SDK poller / Operation-Location header.
Continuation tokens are server-private opaque artifacts: persist them for resume,
never use them as public IDs, and never send them through Agent or browser payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ..runtime_config import azure_settings, snapshot

GA_API_VERSION = "2025-11-01"


class AzureUnavailableError(RuntimeError):
    code = "azure_unavailable"


@dataclass
class AzureJob:
    analyzer_id: str
    api_version: str
    status: str
    operation_id: str | None = None
    continuation_token: str | None = field(default=None, repr=False)
    poller: Any | None = field(default=None, repr=False)
    raw: Any = None
    derived: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None

    def public_dict(self) -> dict[str, Any]:
        derived = self.derived or {}
        markdown = derived.get("markdown") if isinstance(derived, dict) else None
        locators = public_locator_map(derived) if self.status == "succeeded" else []
        return {
            "status": self.status,
            "operation_id": self.operation_id,
            "analyzer_id": self.analyzer_id,
            "api_version": self.api_version,
            "derived": derived if self.status == "succeeded" else None,
            "derived_markdown": markdown if self.status == "succeeded" else None,
            "derived_coordinate_system": "azure_markdown",
            "provider_locators": locators,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


def _operation_id_from_poller(poller: Any) -> str | None:
    getter = getattr(poller, "operation_id", None)
    if isinstance(getter, str) and getter.strip():
        return getter.strip()
    if callable(getter):
        try:
            value = getter()
        except Exception:  # noqa: BLE001
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    try:
        headers = poller.polling_method()._initial_response.http_response.headers  # type: ignore[attr-defined]
        location = headers.get("Operation-Location") or headers.get("operation-location")
    except Exception:  # noqa: BLE001
        location = None
    if not location:
        try:
            response = getattr(getattr(poller, "_pipeline_response", None), "http_response", None)
            if response is not None:
                location = response.headers.get("Operation-Location")
        except Exception:  # noqa: BLE001
            location = None
    if not location:
        return None
    try:
        from azure.ai.contentunderstanding.models._patch import _parse_operation_id

        return _parse_operation_id(location)
    except Exception:  # noqa: BLE001
        path = urlparse(str(location)).path.rstrip("/").split("/")
        return path[-1] if path and path[-1] else None


def _continuation_token(poller: Any, fallback: str | None) -> str | None:
    try:
        token = poller.continuation_token()
    except Exception:  # noqa: BLE001
        token = None
    if isinstance(token, str) and token.strip():
        return token
    return fallback


class AzureContentUnderstanding:
    def __init__(self, client: Any | None = None) -> None:
        self._injected = client
        self._client = client

    def configured(self) -> bool:
        if self._injected is not None:
            return True
        return bool(snapshot()["azure_content_understanding"]["configured"])

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        settings = azure_settings()
        if not settings["endpoint"] or not settings["key"]:
            raise AzureUnavailableError(
                "Azure Content Understanding is not configured. "
                "Set AZURE_CONTENT_UNDERSTANDING_ENDPOINT and AZURE_CONTENT_UNDERSTANDING_KEY."
            )
        from azure.ai.contentunderstanding import ContentUnderstandingClient
        from azure.core.credentials import AzureKeyCredential

        api_version = settings["api_version"] or GA_API_VERSION
        self._client = ContentUnderstandingClient(
            settings["endpoint"],
            AzureKeyCredential(settings["key"]),
            api_version=api_version,
        )
        return self._client

    def start_job(
        self,
        content: bytes,
        *,
        media_type: str | None,
        continuation_token: str | None = None,
    ) -> AzureJob:
        settings = azure_settings()
        analyzer_id = settings["analyzer_id"] or "prebuilt-document"
        api_version = settings["api_version"] or GA_API_VERSION
        client = self._ensure_client()
        content_type = media_type or "application/octet-stream"
        kwargs: dict[str, Any] = {
            "content_type": content_type,
            "polling_interval": 2,
        }
        if continuation_token:
            kwargs["continuation_token"] = continuation_token
        binary = b"" if continuation_token else content
        try:
            # Installed SDK patch sets string_encoding="codePoint" itself.
            poller = client.begin_analyze_binary(analyzer_id, binary, **kwargs)
        except AzureUnavailableError:
            raise
        except TypeError:
            # Injected doubles may use a simpler signature.
            poller = client.begin_analyze_binary(analyzer_id, binary)
        except Exception as exc:  # noqa: BLE001
            raise AzureUnavailableError(
                f"Azure Content Understanding request failed ({type(exc).__name__})."
            ) from exc

        operation_id = _operation_id_from_poller(poller)
        token = _continuation_token(poller, continuation_token)
        return AzureJob(
            analyzer_id=analyzer_id,
            api_version=api_version,
            status="running",
            operation_id=operation_id,
            continuation_token=token,
            poller=poller,
        )

    def wait(self, job: AzureJob, *, timeout_seconds: int = 60) -> AzureJob:
        poller = job.poller
        if poller is None:
            job.status = "failed"
            job.error_code = "missing_poller"
            job.error_message = "No Azure poller is available to wait on."
            return job
        try:
            result = poller.result(timeout=timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            if _is_timeout(exc):
                job.status = "timeout"
                job.error_code = "timeout"
                job.error_message = "Azure Content Understanding job timed out while still running."
                job.continuation_token = _continuation_token(poller, job.continuation_token)
                if not job.operation_id:
                    job.operation_id = _operation_id_from_poller(poller)
                return job
            job.status = "failed"
            job.error_code = type(exc).__name__
            job.error_message = f"Azure Content Understanding job failed ({type(exc).__name__})."
            return job

        if result is None:
            job.status = "failed"
            job.error_code = "empty_result"
            job.error_message = "Azure returned no result; this is not a successful empty analysis."
            return job

        job.operation_id = job.operation_id or _operation_id_from_poller(poller)
        job.continuation_token = _continuation_token(poller, job.continuation_token)
        job.raw = _to_jsonable(result)
        job.derived = derive_representation(job.raw)
        job.status = "succeeded"
        job.error_code = None
        job.error_message = None
        return job

    def analyze_bytes(
        self,
        content: bytes,
        *,
        media_type: str | None,
        continuation_token: str | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        job = self.start_job(content, media_type=media_type, continuation_token=continuation_token)
        if job.status != "running":
            return {**job.public_dict(), "continuation_token": job.continuation_token, "raw": job.raw}
        job = self.wait(job, timeout_seconds=timeout_seconds)
        return {**job.public_dict(), "continuation_token": job.continuation_token, "raw": job.raw}


def _is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return "timeout" in name or "timeout" in text or "polling" in text


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "as_dict"):
        try:
            return value.as_dict()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:  # noqa: BLE001
        return {"repr": type(value).__name__}


MAX_PUBLIC_LOCATORS = 128


def public_locator_map(derived: Any) -> list[dict[str, Any]]:
    """Bounded locator rows for Agent tools. No URLs, tokens, or raw provider secrets."""
    locators: list[Any] = []
    if isinstance(derived, dict):
        raw = derived.get("provider_locators")
        if isinstance(raw, list):
            locators = raw
    out: list[dict[str, Any]] = []
    for index, item in enumerate(locators):
        if not isinstance(item, dict):
            continue
        locator_id = item.get("locator_id") or f"az-loc-{index + 1}"
        original = item.get("original_coordinates")
        has_mapped_original = original == "mapped" and any(
            item.get(key) not in (None, "")
            for key in ("page", "sheet", "cell_ref", "cell", "region")
        )
        out.append(
            {
                "locator_id": str(locator_id),
                "kind": item.get("kind"),
                "page": item.get("page"),
                "sheet": item.get("sheet"),
                "cell_ref": item.get("cell_ref") or item.get("cell"),
                "region": item.get("region"),
                "offset": item.get("offset"),
                "length": item.get("length"),
                "coordinate_system": item.get("coordinate_system") or "azure_markdown",
                "original_coordinates": "mapped" if has_mapped_original else "unknown",
            }
        )
    return out[:MAX_PUBLIC_LOCATORS]


def derive_representation(raw: Any) -> dict[str, Any]:
    """Provider-derived markdown/text plus locator mapping. Not original coordinates."""
    markdown = None
    contents: list = []
    locators: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
        analyze = raw.get("analyzeResult") if isinstance(raw.get("analyzeResult"), dict) else {}
        if isinstance(raw.get("markdown"), str):
            markdown = raw["markdown"]
        elif isinstance(result.get("markdown"), str):
            markdown = result["markdown"]
        elif isinstance(analyze.get("markdown"), str):
            markdown = analyze["markdown"]
        if isinstance(raw.get("contents"), list):
            contents = raw["contents"]
        elif isinstance(result.get("contents"), list):
            contents = result["contents"]
        elif isinstance(analyze.get("contents"), list):
            contents = analyze["contents"]
        for source in (raw, result, analyze):
            spans = source.get("spans") if isinstance(source, dict) else None
            if isinstance(spans, list):
                for item in spans:
                    if isinstance(item, dict):
                        locators.append(
                            {
                                "locator_id": f"az-loc-{len(locators) + 1}",
                                "coordinate_system": "azure_markdown",
                                "offset": item.get("offset"),
                                "length": item.get("length"),
                                "page": item.get("pageNumber") or item.get("page"),
                                "sheet": item.get("sheet"),
                                "cell_ref": item.get("cell_ref") or item.get("cell"),
                                "region": item.get("region"),
                                "kind": item.get("kind") or item.get("type"),
                                "original_coordinates": "unknown",
                            }
                        )
        for content in contents:
            if not isinstance(content, dict) or not isinstance(content.get("spans"), list):
                continue
            for item in content["spans"]:
                if not isinstance(item, dict):
                    continue
                locators.append(
                    {
                        "locator_id": f"az-loc-{len(locators) + 1}",
                        "coordinate_system": "azure_markdown",
                        "offset": item.get("offset"),
                        "length": item.get("length"),
                        "page": (
                            item.get("pageNumber")
                            or item.get("page")
                            or content.get("pageNumber")
                            or content.get("page")
                        ),
                        "sheet": item.get("sheet") or content.get("sheet"),
                        "cell_ref": (
                            item.get("cell_ref")
                            or item.get("cell")
                            or content.get("cell_ref")
                            or content.get("cell")
                        ),
                        "region": item.get("region") or content.get("region"),
                        "kind": (
                            item.get("kind")
                            or item.get("type")
                            or content.get("kind")
                            or content.get("type")
                        ),
                        "original_coordinates": "unknown",
                    }
                )
    text = markdown if isinstance(markdown, str) else None
    if text is None and contents:
        parts = []
        for item in contents:
            if isinstance(item, dict) and isinstance(item.get("markdown"), str):
                parts.append(item["markdown"])
                locators.append(
                    {
                        "locator_id": f"az-loc-{len(locators) + 1}",
                        "coordinate_system": "azure_markdown",
                        "kind": item.get("kind") or item.get("type"),
                        "page": item.get("pageNumber") or item.get("page"),
                        "sheet": item.get("sheet"),
                        "cell_ref": item.get("cell_ref") or item.get("cell"),
                        "region": item.get("region"),
                        "offset": item.get("offset"),
                        "length": item.get("length"),
                        "original_coordinates": "unknown",
                    }
                )
            elif isinstance(item, str):
                parts.append(item)
        text = "\n\n".join(parts) if parts else None
    return {
        "coordinate_system": "azure_markdown",
        "markdown": text,
        "original_coordinates": "unknown",
        "provider_locators": locators,
        "note": (
            "Azure markdown offsets are not automatically original text or Excel coordinates. "
            "Map to originals only when a locator mapping is known."
        ),
        "content_count": len(contents) if isinstance(contents, list) else 0,
    }
