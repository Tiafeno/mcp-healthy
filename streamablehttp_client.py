from typing import Optional
import os
from typing import cast
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from anthropic import Anthropic
from anthropic.types import ImageBlockParam, ToolUnionParam

from utils.logging_config import get_logger


class StreamableHTTPClient:
    def __init__(self, session_token: str, mcp_url: str):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.token = session_token
        self.mcp_url = mcp_url
        self.max_tokens = 1000
        self.model = os.getenv("AI_MODEL", "claude-sonnet-4-5")
        self.logger = get_logger(__name__)

    async def connect_to_server(self):
        """Connect to an MCP server via HTTP transport"""
        server_params = {
            "url": self.mcp_url,
            "headers": {"Authorization": f"Bearer {self.token}"},
        }

        try:
            http_transport = await self.exit_stack.enter_async_context(
                streamablehttp_client(**server_params)
            )
            self.read, self.write, _ = http_transport
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.read, self.write)
            )
            await self.session.initialize()
            self.logger.info("MCP server connection established and initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to MCP server: {e}", exc_info=True)
            raise

    async def list_tools(self) -> list[dict]:
        if not self.session:
            raise RuntimeError("Session not initialized. Call connect_to_server first.")
        try:
            response = await self.session.list_tools()
            return  [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in response.tools
            ]
        except Exception as e:
            return []
            
    async def process_query(
        self, user_message: str, last_message: str | None, document_urls: list[str]
    ):
        if not self.session:
            raise RuntimeError("Session not initialized. Call connect_to_server first.")

        document_sources: list[ImageBlockParam] = [
            {"type": "image", "source": {"type": "url", "url": url}}
            for url in document_urls
        ]

        messages: list = []
        messages.append({"role": "assistant", "content": last_message} if last_message else {"role": "user", "content": (
            "You are a health and nutrition expert. Use the tools of healthy-server to assist users with their dietary needs and health-related inquiries. Provide accurate and helpful information based on the user's questions and the data available through the tools."
        )})
        messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": user_message}] + document_sources,
            }
        )

        available_tools = await self.list_tools()

        # Initial Claude API call
        response = self.anthropic.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=messages,
            tools=available_tools 
        )

        # Process response and handle tool calls
        message: str | None = None
        text_responses = 0
        tool_calls = 0
        
        for content in response.content:
            if content.type == "text":
                text_responses += 1
                self.logger.debug(f"Yielding text response #{text_responses}: {len(content.text)} characters")
                yield content.text
            elif content.type == "tool_use":
                tool_calls += 1
                tool_name = content.name
                tool_args = content.input
                self.logger.info(f"Tool call #{tool_calls}: {tool_name} with args: {tool_args}")

                try:
                    # Execute tool call
                    result = await self.session.call_tool(tool_name, tool_args)  # type: ignore
                    self.logger.debug(f"Tool call {tool_name} executed successfully")
                    
                    # Continue conversation with tool results
                    if hasattr(content, "text") and content.text:
                        messages.append({"role": "assistant", "content": content.text})  # type: ignore
                    messages.append({"role": "user", "content": result.content})

                    # Get next response from Claude
                    response = self.anthropic.messages.create(
                        model=self.model,
                        max_tokens=self.max_tokens,
                        messages=messages,
                    )
                    
                    if response.content and response.content[0].type == "text":
                        message = response.content[0].text
                        
                except Exception as e:
                    self.logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
                    continue

        if message:
            yield message
        
        self.logger.info(f"Query processing completed. Text responses: {text_responses}, Tool calls: {tool_calls}")

    async def process_conversation_title_query(self, assistant_message: str) -> str | None:
        try:
            response = self.anthropic.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "assistant",
                        "content": assistant_message
                    },
                    {
                        "role": "user",
                        "content": "Resume en une seul phrase le sujet principal de la conversation precedente pour servir de titre concis. Sans utiliser de guillemets ou markeurs de citation.",
                    }
                ],
            )
            if response.content and response.content[0].type == "text":
                return response.content[0].text
            return None
        except Exception as e:
            self.logger.error(f"Failed to get response from Claude API: {e}", exc_info=True)
            return None
    
    async def cleanup(self):
        """Clean up resources"""
        self.logger.info("Starting cleanup of StreamableHTTPClient resources")
        try:
            await self.exit_stack.aclose()
            self.logger.debug("Exit stack closed successfully")
            self.session = None
            self.logger.info("StreamableHTTPClient cleanup completed successfully")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}", exc_info=True)
            raise
