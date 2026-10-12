import json


def log(message: str, **fields) -> None:
    """Emit one structured JSON log line (captured by CloudWatch Logs)."""
    print(json.dumps({"message": message, **fields}, default=str))
