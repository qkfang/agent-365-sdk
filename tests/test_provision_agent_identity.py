import json

import httpx
import pytest

from provision_agent_identity import GRAPH_BASE_URL, provision_agent_identity


@pytest.mark.asyncio
async def test_provisions_agent_identity_resources_with_typed_endpoints() -> None:
    requests: list[httpx.Request] = []
    responses = [
        {"id": "blueprint-object-id", "appId": "blueprint-application-id"},
        {"id": "blueprint-principal-object-id"},
        {"id": "agent-object-id", "appId": "agent-application-id"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json=responses[len(requests) - 1])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await provision_agent_identity(
            client,
            access_token="graph-token",
            sponsor_user_id="sponsor-user-id",
            blueprint_display_name="SaaS Agent Blueprint",
            agent_display_name="SaaS Agent Instance",
        )

    assert [request.url.path for request in requests] == [
        "/v1.0/applications/microsoft.graph.agentIdentityBlueprint",
        (
            "/v1.0/servicePrincipals/"
            "microsoft.graph.agentIdentityBlueprintPrincipal"
        ),
        "/v1.0/servicePrincipals/microsoft.graph.agentIdentity",
    ]
    assert all(request.headers["OData-Version"] == "4.0" for request in requests)
    assert all(
        request.headers["Authorization"] == "Bearer graph-token"
        for request in requests
    )
    sponsor_binding = [f"{GRAPH_BASE_URL}/users/sponsor-user-id"]
    assert json.loads(requests[0].content) == {
        "displayName": "SaaS Agent Blueprint",
        "sponsors@odata.bind": sponsor_binding,
    }
    assert json.loads(requests[1].content) == {
        "appId": "blueprint-application-id"
    }
    assert json.loads(requests[2].content) == {
        "displayName": "SaaS Agent Instance",
        "agentIdentityBlueprintId": "blueprint-application-id",
        "sponsors@odata.bind": sponsor_binding,
    }
    assert result.blueprint_application_id == "blueprint-application-id"
    assert result.blueprint_object_id == "blueprint-object-id"
    assert result.blueprint_principal_object_id == "blueprint-principal-object-id"
    assert result.agent_identity_application_id == "agent-application-id"
    assert result.agent_identity_object_id == "agent-object-id"


@pytest.mark.asyncio
async def test_rejects_graph_response_without_required_identifier() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "blueprint-object-id"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="did not include appId"):
            await provision_agent_identity(
                client,
                access_token="graph-token",
                sponsor_user_id="sponsor-user-id",
                blueprint_display_name="SaaS Agent Blueprint",
                agent_display_name="SaaS Agent Instance",
            )