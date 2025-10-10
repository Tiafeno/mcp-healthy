import uvicorn
import os
from sqlmodel import select
from typing import Annotated
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, WebSocketException, status, Header
from dotenv import load_dotenv
load_dotenv()

from models import lifespan, Session, get_session, Message, Conversation

app = FastAPI(lifespan=lifespan)

from mcp_client import MCPClient

# Récupération des variables d'environnement
api_base_url = os.getenv("API_BASE_URL", "https://healthy-ai.test/mcp/healthy")

async def get_ws_token(
    websocket: WebSocket,
    token: Annotated[str | None, Header()] = None,
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
async def websocket_endpoint(websocket: WebSocket, conversation_id: str, token: tokenDep, session: sessionDep):
    await manager.connect(websocket)
    try:
        client = MCPClient(token, api_base_url)
        await client.connect_to_server()
        
        last_message_text: str | None = None
        statement = select(Message) \
            .where(Message.conversation_id == conversation_id) \
            .where(Message.role == "assistant") \
            .order_by(Message.created_at.desc())
        last_message = session.exec(statement).first()
        if last_message:
            last_message_text = last_message.content
            
        while True:
            message_received = await websocket.receive_text()
            try:
                message = Message(
                    conversation_id=conversation_id,
                    role="user",
                    content=message_received,
                    created_at="now()",
                )
                session.add(message)
                # Process the query and get the response
                response = await client.process_query(message_received, last_message_text)
                await manager.send_personal_message(response, websocket)
                response_message = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=response,
                    created_at="now()",
                )
                session.add(response_message)
                session.commit()
            finally:
                await client.cleanup()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"Client #{conversation_id} left the chat")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
        access_log=True,
        reload=True,
    )