from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agent_identity import AgentIdentityTokenProvider


@pytest.mark.asyncio
async def test_requests_token_for_agent_identity() -> None:
    response = httpx.Response(
        200,
        json={"authorizationHeader": "Bearer agent-token"},
        request=httpx.Request("GET", "http://sidecar"),
    )
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client

    with patch("agent_identity.httpx.AsyncClient", return_value=client):
        provider = AgentIdentityTokenProvider(
            sidecar_url="http://sidecar:5000/",
            agent_identity_client_id="agent-app-id",
        )
        token = await provider.get_authorization_header()

    assert token == "Bearer agent-token"
    client.get.assert_awaited_once_with(
        "http://sidecar:5000/AuthorizationHeaderUnauthenticated/Toolbox",
        params={"AgentIdentity": "agent-app-id"},
    )


@pytest.mark.asyncio
async def test_rejects_missing_bearer_token() -> None:
    response = httpx.Response(
        200,
        json={},
        request=httpx.Request("GET", "http://sidecar"),
    )
    client = AsyncMock()
    client.get.return_value = response
    client.__aenter__.return_value = client

    with patch("agent_identity.httpx.AsyncClient", return_value=client):
        provider = AgentIdentityTokenProvider("http://sidecar", "agent-app-id")
        with pytest.raises(RuntimeError, match="no bearer token"):
            await provider.get_authorization_header()