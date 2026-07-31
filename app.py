from __future__ import annotations

import asyncio
import os

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
from microsoft_agents_a365.observability.core import configure
from microsoft_agents_a365.observability.extensions.agentframework import (
    AgentFrameworkInstrumentor,
)

from agent_identity import AgentIdentityAuth, AgentIdentityTokenProvider


def required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Set {name} in the environment")
    return value


async def main() -> None:
    load_dotenv()

    configure(
        service_name="external-saas-agent",
        service_namespace="agent365.samples",
    )
    AgentFrameworkInstrumentor().instrument()

    token_provider = AgentIdentityTokenProvider(
        sidecar_url=os.getenv("AGENTID_SIDECAR_URL", "http://localhost:5000"),
        agent_identity_client_id=required_setting("AGENT_IDENTITY_CLIENT_ID"),
    )

    credential = DefaultAzureCredential()
    async with httpx.AsyncClient(
        auth=AgentIdentityAuth(token_provider),
        timeout=120.0,
    ) as toolbox_client:
        toolbox = MCPStreamableHTTPTool(
            name="foundry-toolbox",
            url=required_setting("TOOLBOX_ENDPOINT"),
            http_client=toolbox_client,
            load_prompts=False,
        )
        chat_client = OpenAIChatClient(
            azure_endpoint=required_setting("AZURE_OPENAI_ENDPOINT"),
            model=required_setting("AZURE_OPENAI_DEPLOYMENT_NAME"),
            api_version=required_setting("AZURE_OPENAI_API_VERSION"),
            credential=credential,
        )

        async with toolbox:
            agent = Agent(
                client=chat_client,
                name="external-saas-agent",
                instructions=(
                    "You are a concise assistant. Use the Foundry toolbox when "
                    "it can answer the request. Do not invoke tools that require "
                    "approval unless the user has explicitly approved the action."
                ),
                tools=[toolbox],
            )

            print("Agent ready. Enter a message, or 'quit' to stop.")
            while (message := input("> ").strip()).lower() not in {"quit", "exit"}:
                if message:
                    result = await agent.run(message)
                    print(result.text)

    await credential.close()


if __name__ == "__main__":
    asyncio.run(main())