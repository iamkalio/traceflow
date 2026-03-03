from typing import Any

_config: dict[str, Any] = {"endpoint": "", "enabled": True, "attributes": {}}


def get() -> dict[str, Any]:
    return _config
