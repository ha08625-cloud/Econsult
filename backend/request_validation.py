from errors import INVALID_PAYLOAD


def require_keys(obj: dict, allowed: set):
    extra = set(obj.keys()) - allowed
    if extra:
        raise INVALID_PAYLOAD(f"Illegal fields present: {extra}")


def validate_init_payload(payload: dict):
    require_keys(payload, {"condition_id", "free_text"})
    if not isinstance(payload["condition_id"], str):
        raise INVALID_PAYLOAD("condition_id must be string")


def validate_update_payload(payload: dict):
    require_keys(payload, {"runtime_id", "base_version", "answers", "additional_text"})

    if not isinstance(payload["runtime_id"], str):
        raise INVALID_PAYLOAD("runtime_id must be string")

    if not isinstance(payload["base_version"], int):
        raise INVALID_PAYLOAD("base_version must be integer")

    if not isinstance(payload["answers"], dict):
        raise INVALID_PAYLOAD("answers must be object")

    if not payload["answers"]:
        raise INVALID_PAYLOAD("answers must be complete and non-empty")

    additional_text = payload.get("additional_text")
    if additional_text is not None and not isinstance(additional_text, str):
        raise INVALID_PAYLOAD("additional_text must be a string or null")


def validate_finish_payload(payload: dict):
    require_keys(payload, {"runtime_id", "version"})

    if not isinstance(payload["runtime_id"], str):
        raise INVALID_PAYLOAD("runtime_id must be string")

    if not isinstance(payload["version"], int):
        raise INVALID_PAYLOAD("version must be integer")