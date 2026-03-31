"""
shared/event_bus.py
────────────────────
Thin abstraction over the transport between services.

TODAY  → reads/writes JSON files in a local data/ folder.
FUTURE → swap the body of `publish` and `consume` to use
          RabbitMQ (pika), Kafka (confluent-kafka), or Redis Streams.
          No other file needs to change.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Where JSON event files are written/read by default.
# Override via config.py in each service if needed.
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


def publish(event_name: str, payload: BaseModel, data_dir: Path = _DEFAULT_DATA_DIR) -> Path:
    """
    Publish an event by serialising the Pydantic model to a JSON file.

    Args:
        event_name:  e.g. "ocr_completed" or "nlp_completed"
        payload:     any Pydantic model (OcrDocument, NlpDocument, …)
        data_dir:    folder to write into (created if missing)

    Returns:
        Path of the written file.

    Future microservice swap:
        Replace the file-write with a message-queue publish call.
        Keep the function signature identical so callers don't change.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / f"{event_name}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(payload.model_dump_json(indent=2))

    print(f"[event_bus] published → {out_path}")
    return out_path


def consume(event_name: str, model: Type[T], data_dir: Path = _DEFAULT_DATA_DIR) -> T:
    """
    Consume an event by reading and deserialising a JSON file.

    Args:
        event_name:  e.g. "ocr_completed"
        model:       Pydantic model class to deserialise into
        data_dir:    folder to read from

    Returns:
        Validated Pydantic model instance.

    Raises:
        FileNotFoundError if the event file doesn't exist yet.

    Future microservice swap:
        Replace the file-read with a queue consumer / subscriber.
        Keep the function signature identical so callers don't change.
    """
    in_path = data_dir / f"{event_name}.json"

    if not in_path.exists():
        raise FileNotFoundError(
            f"[event_bus] event file not found: {in_path}\n"
            f"Make sure the upstream service has run first."
        )

    with open(in_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    print(f"[event_bus] consumed ← {in_path}")
    return model.model_validate(raw)
