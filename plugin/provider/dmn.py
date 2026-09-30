from typing import Any
from dify_plugin import ToolProvider


class DMNProvider(ToolProvider):
    """Legacy provider identity retained for an explicit breaking upgrade."""

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # No service, token, account, filesystem or network access is required.
        return None
