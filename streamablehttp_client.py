from typing import Optional
import os
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from anthropic import Anthropic
from anthropic.types import ImageBlockParam, beta

from models import Documents


class StreamableHTTPClient:
    def __init__(self, session_token: str, mcp_url: str):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.token = session_token
        self.mcp_url = mcp_url
        self.max_tokens = 1000

    async def connect_to_server(self):
        """Connect to an MCP server via HTTP transport"""
        server_params = {
            "url": self.mcp_url,
            "headers": {"Authorization": f"Bearer {self.token}"},
        }

        http_transport = await self.exit_stack.enter_async_context(
            streamablehttp_client(**server_params)
        )
        self.read, self.write, _ = http_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.read, self.write)
        )
        await self.session.initialize()

    async def process_query(
        self, user_message: str, last_message: str | None, document_urls: list[str]
    ):
        """Process a query using Claude and available tools"""
        if not self.session:
            raise RuntimeError("Session not initialized. Call connect_to_server first.")

        messages: list = []
        if last_message:
            messages.append({"role": "assistant", "content": last_message})
        else:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You are a health and nutrition expert. Use the tools of healthy-server to assist users with their dietary needs and health-related inquiries. Provide accurate and helpful information based on the user's questions and the data available through the tools."
                    ),
                }
            )

        document_sources: list[ImageBlockParam] = [
            {"type": "image", "source": {"type": "url", "url": url}}
            for url in document_urls
        ]
        messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": user_message}] + document_sources,
            }
        )
        response = await self.session.list_tools()
        available_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in response.tools
        ]

        # Initial Claude API call
        response = self.anthropic.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=messages,
            tools=available_tools,
        )

        # Process response and handle tool calls
        final_text = []

        for content in response.content:
            if content.type == "text":
                final_text.append(content.text)
            elif content.type == "tool_use":
                tool_name = content.name
                tool_args = content.input

                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)

                # Continue conversation with tool results
                if hasattr(content, "text") and content.text:
                    messages.append({"role": "assistant", "content": content.text})
                messages.append({"role": "user", "content": result.content})

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)

    def upload_file(
        self, file_path: str, file_name: str, mime_type: str
    ) -> beta.FileMetadata:
        """Upload a file to the MCP server and return its metadata"""
        if not self.session:
            raise RuntimeError("Session not initialized. Call connect_to_server first.")

        with open(file_path, "rb") as f:
            response = self.anthropic.beta.files.upload(file=(file_name, f, mime_type))
            f.close()
        return response

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()
