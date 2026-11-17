from typing import Any


class PayloadRecorder:
    """Holds big span payloads (inputs, outputs, prompts) keyed by OTel span_id.

    OTel span attributes only take primitives, so the orchestrator records
    payloads here and the exporter merges them at export time.
    """

    def __init__(self) -> None:
        self._payloads: dict[int, dict[str, Any]] = {}

    def record(self, span_id: int, **payload: Any) -> None:
        self._payloads.setdefault(span_id, {}).update(payload)

    def pop(self, span_id: int) -> dict[str, Any]:
        return self._payloads.pop(span_id, {})
