from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from pydantic import BaseModel

from app.analysis.schemas import AnalysisBatchResult


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def analysis_cache_key(
    *,
    protocol: str,
    provider_config_generation: int,
    model: str,
    content_hash: str,
    prompt_hash: str,
    schema_version: str,
    pipeline_version: str,
    parameters: dict[str, Any],
) -> str:
    canonical = _canonical_json(
        {
            "protocol": protocol,
            "provider_config_generation": provider_config_generation,
            "model": model,
            "content_hash": content_hash,
            "prompt_hash": prompt_hash,
            "schema_version": schema_version,
            "pipeline_version": pipeline_version,
            "parameters": parameters,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AIResultCache:
    _DIAGNOSTIC_FIELDS = {
        "protocol",
        "provider_config_generation",
        "model",
        "cache_usage_reported",
        "cached_input_tokens",
        "cache_creation_input_tokens",
    }

    def __init__(self, root: Path, result_type: type[BaseModel] = AnalysisBatchResult):
        self.root = root.resolve()
        self.result_type = result_type
        self.root.mkdir(parents=True, exist_ok=True)

    def _result_path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def _index_path(self, key: str) -> Path:
        return self.root / "index" / f"{key}.json"

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(_canonical_json(payload))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self, key: str) -> BaseModel | None:
        path = self._result_path(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return self.result_type.model_validate(payload["result"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            return None

    def store(
        self,
        key: str,
        result: BaseModel,
        *,
        status: str,
        metadata: dict[str, Any],
    ) -> bool:
        if status != "succeeded":
            return False
        result_path = self._result_path(key)
        self._atomic_json(
            result_path,
            {
                "key": key,
                "result": result.model_dump(mode="json"),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        diagnostic = {
            field: metadata[field] for field in sorted(self._DIAGNOSTIC_FIELDS) if field in metadata
        }
        diagnostic.update({"key": key, "created_at": datetime.now(UTC).isoformat()})
        self._atomic_json(self._index_path(key), diagnostic)
        return True

    def clear(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
