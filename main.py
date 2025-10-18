import uvicorn
import os
import json
from sqlmodel import select
from typing import Annotated
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    WebSocketException,
    status,
    Query,
)
from dotenv import load_dotenv

load_dotenv()

from models import lifespan, Session, get_session, Message, Documents

app = FastAPI(lifespan=lifespan)

from streamablehttp_client import StreamableHTTPClient

# Récupération des variables d'environnement
mcp_streaming_url = os.getenv(
    "MCP_STREAMING_HTTP_URL", "https://healthy-ai.test/mcp/healthy"
)


async def get_ws_token(
    websocket: WebSocket,
    token: Annotated[str | None, Query()] = None,
):
    if token is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return token


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()

# Depends
sessionDep = Annotated[Session, Depends(get_session)]
tokenDep = Annotated[str, Depends(get_ws_token)]


@app.websocket("/ws/{user_id}/conversations/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket, conversation_id: str, token: tokenDep, session: sessionDep
):
    await manager.connect(websocket)
    try:
        client = StreamableHTTPClient(token, mcp_streaming_url)
        await client.connect_to_server()

        last_message_text: str | None = None
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.role == "assistant")
            .order_by(Message.created_at.desc())  # type: ignore
        )
        last_message = session.exec(statement).first()
        if last_message:
            last_message_text = last_message.content

        while True:
            message_received = (await websocket.receive_text())  # format {"message": "text", attachments: [...]}
            try:
                message_data = json.loads(message_received)
            except json.JSONDecodeError:
                await manager.send_personal_message("Invalid message format", websocket)
                continue
            message_content = message_data.get("message", "")
            message_attachments = message_data.get("attachments", [])

            if not message_content or len(message_content.strip()) <= 2:
                await manager.send_personal_message("Message content is required", websocket)
                continue
            urls = list()

            try:
                message = Message(
                    conversation_id=conversation_id,
                    role="user",
                    content=message_content,
                    created_at="now()",  # type: ignore
                )
                session.add(message)
                session.commit()

                if message_attachments is not None and len(message_attachments) > 0:
                    documents = [
                        await get_document_by_id(att_id, session)
                        for att_id in message_attachments
                    ]
                    for doc in [d for d in documents if d is not None]:
                        path = await get_document_download_url(doc, token)
                        urls.append(path)
                        # Update document to link attachments to message
                        doc.message_uuid = message.uuid
                        session.add(doc)
                        session.commit()

                # Process the query and get the response
                response = await client.process_query(message_content, last_message_text, urls)
                await manager.send_personal_message(response, websocket)
                response_message = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=response,
                    created_at="now()",  # type: ignore
                )
                session.add(response_message)
                session.commit()
            except Exception as e:
                await manager.send_personal_message(f"Error processing message: {e}", websocket)
                continue

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"Client #{conversation_id} left the chat")
    finally:
        await client.cleanup()

async def get_document_by_id(
    attachment_id: int, session: sessionDep
) -> Documents | None:
    try:
        document = session.get(Documents, attachment_id)
        return document if document else None
    except Exception as e:
        print(f"Error fetching document with id {attachment_id}: {e}")
        return None

async def get_document_download_url(document: Documents, token: str) -> str | None:
    api_base_path = os.getenv("API_BASE_URL")
    return (
        f"{api_base_path}/api/documents/{document.id}/download?access_token={token}"
        if document
        else None
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        workers=1,
        access_log=True,
        reload=True,
    )
