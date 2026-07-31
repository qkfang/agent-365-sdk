from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class AgentIdentityTokenProvider:
    sidecar_url: str
    agent_identity_client_id: str
    downstream_api: str = "Toolbox"

    async def get_authorization_header(self) -> str:
        url = (
            f"{self.sidecar_url.rstrip('/')}"
            f"/AuthorizationHeaderUnauthenticated/{self.downstream_api}"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params={"AgentIdentity": self.agent_identity_client_id},
            )
            response.raise_for_status()

        authorization_header = response.json().get("authorizationHeader", "")
        if not authorization_header.startswith("Bearer "):
            raise RuntimeError("AgentID sidecar returned no bearer token")
        return authorization_header


class AgentIdentityAuth(httpx.Auth):
    def __init__(self, token_provider: AgentIdentityTokenProvider) -> None:
        self._token_provider = token_provider

    async def async_auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = (
            await self._token_provider.get_authorization_header()
        )
        yield request