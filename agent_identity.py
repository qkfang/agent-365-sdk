from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import time

import httpx


TOKEN_SCOPE = "api://AzureADTokenExchange/.default"
CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


@dataclass
class AgentIdentityTokenProvider:
    tenant_id: str
    blueprint_client_id: str
    agent_identity_client_id: str
    blueprint_client_secret: str | None = None
    blueprint_assertion_file: str | None = None
    scope: str = "https://ai.azure.com/.default"

    def __post_init__(self) -> None:
        if bool(self.blueprint_client_secret) == bool(self.blueprint_assertion_file):
            raise ValueError(
                "Set exactly one blueprint credential: client secret or assertion file"
            )
        self._authorization_header = ""
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    def _blueprint_credential(self) -> dict[str, str]:
        if self.blueprint_client_secret:
            return {"client_secret": self.blueprint_client_secret}

        assertion = Path(self.blueprint_assertion_file or "").read_text().strip()
        if not assertion:
            raise RuntimeError("Blueprint assertion file is empty")
        return {
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": assertion,
        }

    async def get_authorization_header(self) -> str:
        if self._authorization_header and time.time() < self._expires_at - 60:
            return self._authorization_header

        async with self._lock:
            if self._authorization_header and time.time() < self._expires_at - 60:
                return self._authorization_header

            token_url = (
                f"https://login.microsoftonline.com/{self.tenant_id}"
                "/oauth2/v2.0/token"
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                parent_response = await client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.blueprint_client_id,
                        "scope": TOKEN_SCOPE,
                        "fmi_path": self.agent_identity_client_id,
                        **self._blueprint_credential(),
                    },
                )
                parent_response.raise_for_status()

                response = await client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.agent_identity_client_id,
                        "client_assertion_type": CLIENT_ASSERTION_TYPE,
                        "client_assertion": parent_response.json()["access_token"],
                        "scope": self.scope,
                    },
                )
                response.raise_for_status()

            token = response.json()
            access_token = token.get("access_token", "")
            if not access_token:
                raise RuntimeError("Agent Identity exchange returned no access token")

            self._authorization_header = f"Bearer {access_token}"
            self._expires_at = time.time() + int(token.get("expires_in", 0))
            return self._authorization_header


class AgentIdentityAuth(httpx.Auth):
    def __init__(self, token_provider: AgentIdentityTokenProvider) -> None:
        self._token_provider = token_provider

    async def async_auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = (
            await self._token_provider.get_authorization_header()
        )
        yield request