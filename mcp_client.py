from typing import Optional
import os
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from anthropic import Anthropic
from anthropic.types import MessageParam

class MCPClient:
    def __init__(self, token: str, api_base_url: str):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.token = token
        self.api_base_url = api_base_url

    async def connect_to_server(self):
        """Connect to an MCP server via HTTP transport"""
        server_params = {
            "url": self.api_base_url,
            "headers": {
                "Authorization": f"Bearer {self.token}"
            }
        }

        http_transport = await self.exit_stack.enter_async_context(streamablehttp_client(**server_params))
        self.read, self.write, _ = http_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.read, self.write))

        await self.session.initialize()
        
        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, user_message: str, last_message: str | None) -> str:
        """Process a query using Claude and available tools"""
        if not self.session:
            raise RuntimeError("Session not initialized. Call connect_to_server first.")

        messages: list[MessageParam] = []
        if last_message:
            messages.append({"role": "assistant", "content": last_message})
        messages.append({"role": "user", "content": user_message})
        response = await self.session.list_tools()
        available_tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

        # Initial Claude API call
        response = self.anthropic.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=messages,
            tools=available_tools
        )
        
        # Process response and handle tool calls
        final_text = []

        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input
                
                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                # Continue conversation with tool results
                if hasattr(content, 'text') and content.text:
                    messages.append({
                      "role": "assistant",
                      "content": content.text
                    })
                messages.append({
                    "role": "user", 
                    "content": result.content
                })

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()
