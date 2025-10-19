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

# Configuration du logging (doit être fait au début)
from utils.logging_config import setup_logging, get_logger
from utils.logging_middleware import LoggingMiddleware, websocket_logger

# Initialiser le système de logging
app_logger = setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_dir=os.getenv("LOG_DIR", "logs"),
    app_name=os.getenv("APP_NAME", "healthy-mcp")
)

from models import lifespan, Session, get_session, Message, Documents

app = FastAPI(lifespan=lifespan)

# Ajouter le middleware de logging
app.add_middleware(LoggingMiddleware)

# Logger pour ce module
logger = get_logger(__name__)

from streamablehttp_client import StreamableHTTPClient

# Récupération des variables d'environnement
mcp_streaming_url = os.getenv(
    "MCP_STREAMING_HTTP_URL", "https://healthy-ai.test/mcp/healthy"
)

logger.info(f"Configuration MCP Streaming URL: {mcp_streaming_url}")


async def get_ws_token(
    websocket: WebSocket,
    token: Annotated[str | None, Query()] = None,
):
    if token is None:
        logger.warning("WebSocket connection attempt without token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    logger.debug("WebSocket token validation successful")
    return token


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.logger = get_logger("healthy-mcp.websocket.manager")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        websocket_id = id(websocket)
        client_ip = websocket.client.host if websocket.client else "Unknown"
        websocket_logger.log_connection(str(websocket_id), client_ip)
        self.logger.info(f"Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            websocket_id = id(websocket)
            websocket_logger.log_disconnection(str(websocket_id))
            self.logger.info(f"Active connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str | dict, websocket: WebSocket):
        try:
            data = json.dumps(message) if isinstance(message, dict) else message
            await websocket.send_text(data)
            websocket_id = id(websocket)
            message_type = type(message).__name__
            websocket_logger.log_message_sent(str(websocket_id), message_type, len(data))
        except Exception as e:
            websocket_id = id(websocket)
            websocket_logger.log_error(str(websocket_id), e)
            raise

    async def broadcast(self, message: str):
        self.logger.info(f"Broadcasting message to {len(self.active_connections)} connections")
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                websocket_id = id(connection)
                websocket_logger.log_error(str(websocket_id), e)
                self.disconnect(connection)


manager = ConnectionManager()

# Depends
sessionDep = Annotated[Session, Depends(get_session)]
tokenDep = Annotated[str, Depends(get_ws_token)]


@app.websocket("/ws/{user_id}/conversations/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket, conversation_id: str, token: tokenDep, session: sessionDep
):
    websocket_id = str(id(websocket))
    ws_logger = get_logger("healthy-mcp.websocket.endpoint")
    
    try:
        ws_logger.info(f"WebSocket connection attempt for conversation {conversation_id}")
        await manager.connect(websocket)
        client = StreamableHTTPClient(token, mcp_streaming_url)
        await client.connect_to_server()
        ws_logger.info(f"StreamableHTTPClient connected for conversation {conversation_id}")

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
            ws_logger.debug(f"Last message found for conversation {conversation_id}")

        while True:
            message_received = (
                await websocket.receive_text()
            )  # format {"message": "text", attachments: [...]}
            
            websocket_logger.log_message_received(websocket_id, "text", len(message_received))
            
            try:
                message_data = json.loads(message_received)
            except json.JSONDecodeError as e:
                ws_logger.warning(f"Invalid JSON received: {e}")
                await manager.send_personal_message("Invalid message format", websocket)
                continue
            
            message_content = message_data.get("message", "")
            message_attachments = message_data.get("attachments", [])

            if not message_content or len(message_content.strip()) <= 2:
                ws_logger.warning("Empty or too short message received")
                await manager.send_personal_message(
                    "Message content is required", websocket
                )
                continue
            
            ws_logger.info(f"Processing message for conversation {conversation_id}: {len(message_content)} chars")
            urls = list()

            await typing_indicator(True, websocket)
            try:
                message = Message(
                    conversation_id=conversation_id,
                    role="user",
                    content=message_content,
                    created_at="now()",  # type: ignore
                )
                session.add(message)
                session.commit()
                ws_logger.debug(f"User message saved to database: {message.uuid}")
                
                # Send user message back to client
                await manager.send_personal_message(message.dict(), websocket)

                if message_attachments is not None and len(message_attachments) > 0:
                    ws_logger.info(f"Processing {len(message_attachments)} attachments")
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
                    ws_logger.debug(f"Processed {len(urls)} document URLs")

                # Process the query and get the response
                response_count = 0
                async for response in client.process_query(message_content, last_message_text, urls):
                    if response is None:
                        continue
                    response_count += 1
                    response_message = Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=response,
                        created_at="now()",  # type: ignore
                    )
                    session.add(response_message)
                    session.commit()

                    last_message_text = response_message.content
                    await manager.send_personal_message(response_message.dict(), websocket)

                ws_logger.info(f"Query processed successfully, {response_count} responses sent")
                await typing_indicator(False, websocket)

            except Exception as e:
                ws_logger.error(f"Error processing message: {e}", exc_info=True)
                await manager.send_personal_message(
                    f"Error processing message: {e}", websocket
                )
                await typing_indicator(False, websocket)
                continue

    except WebSocketDisconnect:
        ws_logger.info(f"WebSocket disconnected for conversation {conversation_id}")
        manager.disconnect(websocket)
        await manager.broadcast(f"Client #{conversation_id} left the chat")
    except Exception as e:
        ws_logger.error(f"Unexpected error in WebSocket endpoint: {e}", exc_info=True)
        manager.disconnect(websocket)
    finally:
        if 'client' in locals():
            await client.cleanup()
            ws_logger.debug("StreamableHTTPClient cleanup completed")
            
async def typing_indicator(status: bool, websocket: WebSocket):
    await manager.send_personal_message({"type": "typing", "status": status}, websocket)

async def get_document_by_id(
    attachment_id: int, session: sessionDep
) -> Documents | None:
    db_logger = get_logger("healthy-mcp.database")
    try:
        db_logger.debug(f"Fetching document with id {attachment_id}")
        document = session.get(Documents, attachment_id)
        if document:
            db_logger.debug(f"Document found: {document.name}")
        else:
            db_logger.warning(f"Document not found with id {attachment_id}")
        return document
    except Exception as e:
        db_logger.error(f"Error fetching document with id {attachment_id}: {e}", exc_info=True)
        return None

async def get_document_download_url(document: Documents, token: str) -> str | None:
    api_logger = get_logger("healthy-mcp.api")
    try:
        api_base_path = os.getenv("API_BASE_URL")
        if not api_base_path:
            api_logger.error("API_BASE_URL environment variable not set")
            return None
        
        url = f"{api_base_path}/api/documents/{document.id}/download?access_token={token}"
        api_logger.debug(f"Generated download URL for document {document.id}")
        return url
    except Exception as e:
        api_logger.error(f"Error generating download URL for document {document.id}: {e}")
        return None


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        workers=1,
        access_log=True,
        reload=True,
    )
