from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import json
import os

import httpx
from azure.identity.aio import ClientSecretCredential
from dotenv import load_dotenv


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


@dataclass(frozen=True)
class ProvisionedAgentIdentity:
    blueprint_application_id: str
    blueprint_object_id: str
    blueprint_principal_object_id: str
    agent_identity_application_id: str
    agent_identity_object_id: str


def _required_value(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Microsoft Graph response did not include {name}")
    return value


async def provision_agent_identity(
    client: httpx.AsyncClient,
    access_token: str,
    sponsor_user_id: str,
    blueprint_display_name: str,
    agent_display_name: str,
) -> ProvisionedAgentIdentity:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "OData-Version": "4.0",
    }
    sponsor_binding = [f"{GRAPH_BASE_URL}/users/{sponsor_user_id}"]

    blueprint_response = await client.post(
        f"{GRAPH_BASE_URL}/applications/microsoft.graph.agentIdentityBlueprint",
        headers=headers,
        json={
            "displayName": blueprint_display_name,
            "sponsors@odata.bind": sponsor_binding,
        },
    )
    blueprint_response.raise_for_status()
    blueprint = blueprint_response.json()
    blueprint_application_id = _required_value(blueprint, "appId")

    principal_response = await client.post(
        (
            f"{GRAPH_BASE_URL}/servicePrincipals/"
            "microsoft.graph.agentIdentityBlueprintPrincipal"
        ),
        headers=headers,
        json={"appId": blueprint_application_id},
    )
    principal_response.raise_for_status()
    principal = principal_response.json()

    agent_response = await client.post(
        f"{GRAPH_BASE_URL}/servicePrincipals/microsoft.graph.agentIdentity",
        headers=headers,
        json={
            "displayName": agent_display_name,
            "agentIdentityBlueprintId": blueprint_application_id,
            "sponsors@odata.bind": sponsor_binding,
        },
    )
    agent_response.raise_for_status()
    agent = agent_response.json()

    return ProvisionedAgentIdentity(
        blueprint_application_id=blueprint_application_id,
        blueprint_object_id=_required_value(blueprint, "id"),
        blueprint_principal_object_id=_required_value(principal, "id"),
        agent_identity_application_id=_required_value(agent, "appId"),
        agent_identity_object_id=_required_value(agent, "id"),
    )


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Set {name} in the environment for Python client-credential setup, "
            "or use provision_agent_identity.ps1 for interactive sign-in"
        )
    return value


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Provision a blueprint, blueprint principal, and SaaS agent identity."
    )
    parser.add_argument("--blueprint-name", required=True)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument(
        "--sponsor-user-id",
        default=os.getenv("AGENT_ID_SETUP_SPONSOR_USER_ID"),
        required=not os.getenv("AGENT_ID_SETUP_SPONSOR_USER_ID"),
        help="Microsoft Entra object ID of the sponsoring user.",
    )
    args = parser.parse_args()

    credential = ClientSecretCredential(
        tenant_id=_required_environment("ENTRA_TENANT_ID"),
        client_id=_required_environment("AGENT_ID_SETUP_CLIENT_ID"),
        client_secret=_required_environment("AGENT_ID_SETUP_CLIENT_SECRET"),
    )
    try:
        token = await credential.get_token(GRAPH_SCOPE)
        async with httpx.AsyncClient(timeout=30.0) as client:
            result = await provision_agent_identity(
                client=client,
                access_token=token.token,
                sponsor_user_id=args.sponsor_user_id,
                blueprint_display_name=args.blueprint_name,
                agent_display_name=args.agent_name,
            )
    finally:
        await credential.close()

    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    asyncio.run(main())