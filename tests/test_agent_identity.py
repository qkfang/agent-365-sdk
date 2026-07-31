from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agent_identity import AgentIdentityTokenProvider


@pytest.mark.asyncio
async def test_requests_token_for_agent_identity() -> None:
    parent_response = httpx.Response(
        200,
        json={"access_token": "parent-token"},
        request=httpx.Request("POST", "https://login.microsoftonline.com"),
    )
    agent_response = httpx.Response(
        200,
        json={"access_token": "agent-token", "expires_in": 3600},
        request=httpx.Request("POST", "https://login.microsoftonline.com"),
    )
    client = AsyncMock()
    client.post.side_effect = [parent_response, agent_response]
    client.__aenter__.return_value = client

    with patch("agent_identity.httpx.AsyncClient", return_value=client):
        provider = AgentIdentityTokenProvider(
            tenant_id="tenant-id",
            blueprint_client_id="blueprint-app-id",
            agent_identity_client_id="agent-app-id",
            blueprint_client_secret="blueprint-secret",
        )
        token = await provider.get_authorization_header()

    assert token == "Bearer agent-token"
    assert client.post.await_args_list[0].args == (
        "https://login.microsoftonline.com/tenant-id/oauth2/v2.0/token",
    )
    assert client.post.await_args_list[0].kwargs["data"] == {
        "grant_type": "client_credentials",
        "client_id": "blueprint-app-id",
        "client_secret": "blueprint-secret",
        "scope": "api://AzureADTokenExchange/.default",
        "fmi_path": "agent-app-id",
    }
    assert client.post.await_args_list[1].kwargs["data"] == {
        "grant_type": "client_credentials",
        "client_id": "agent-app-id",
        "client_assertion_type": (
            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
        ),
        "client_assertion": "parent-token",
        "scope": "https://ai.azure.com/.default",
    }


@pytest.mark.asyncio
async def test_reuses_unexpired_agent_token() -> None:
    parent_response = httpx.Response(
        200,
        json={"access_token": "parent-token"},
        request=httpx.Request("POST", "https://login.microsoftonline.com"),
    )
    agent_response = httpx.Response(
        200,
        json={"access_token": "agent-token", "expires_in": 3600},
        request=httpx.Request("POST", "https://login.microsoftonline.com"),
    )
    client = AsyncMock()
    client.post.side_effect = [parent_response, agent_response]
    client.__aenter__.return_value = client

    with patch("agent_identity.httpx.AsyncClient", return_value=client):
        provider = AgentIdentityTokenProvider(
            "tenant-id", "blueprint-app-id", "agent-app-id", "blueprint-secret"
        )
        assert await provider.get_authorization_header() == "Bearer agent-token"
        assert await provider.get_authorization_header() == "Bearer agent-token"

    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_rejects_missing_bearer_token() -> None:
    parent_response = httpx.Response(
        200,
        json={"access_token": "parent-token"},
        request=httpx.Request("POST", "https://login.microsoftonline.com"),
    )
    agent_response = httpx.Response(
        200,
        json={},
        request=httpx.Request("POST", "https://login.microsoftonline.com"),
    )
    client = AsyncMock()
    client.post.side_effect = [parent_response, agent_response]
    client.__aenter__.return_value = client

    with patch("agent_identity.httpx.AsyncClient", return_value=client):
        provider = AgentIdentityTokenProvider(
            "tenant-id", "blueprint-app-id", "agent-app-id", "blueprint-secret"
        )
        with pytest.raises(RuntimeError, match="no access token"):
            await provider.get_authorization_header()


def test_requires_exactly_one_blueprint_credential() -> None:
    with pytest.raises(ValueError, match="exactly one blueprint credential"):
        AgentIdentityTokenProvider("tenant-id", "blueprint-app-id", "agent-app-id")

    with pytest.raises(ValueError, match="exactly one blueprint credential"):
        AgentIdentityTokenProvider(
            "tenant-id",
            "blueprint-app-id",
            "agent-app-id",
            blueprint_client_secret="secret",
            blueprint_assertion_file="assertion.txt",
        )


def test_reads_federated_blueprint_assertion(tmp_path) -> None:
    assertion_file = tmp_path / "assertion.jwt"
    assertion_file.write_text("workload-assertion\n")
    provider = AgentIdentityTokenProvider(
        "tenant-id",
        "blueprint-app-id",
        "agent-app-id",
        blueprint_assertion_file=str(assertion_file),
    )

    assert provider._blueprint_credential() == {
        "client_assertion_type": (
            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
        ),
        "client_assertion": "workload-assertion",
    }