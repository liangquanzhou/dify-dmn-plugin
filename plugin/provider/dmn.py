from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from client import DMNError, EngineClient


class DMNProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            EngineClient(credentials).health()
        except DMNError as exc:
            raise ToolProviderCredentialValidationError(str(exc)) from None
