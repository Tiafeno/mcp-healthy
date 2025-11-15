import uvicorn
import os
import json
from sqlmodel import select
from typing import Annotated
from anthropic.types import (
    TextBlock
)
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

load_dotenv(".env")
load_dotenv(".env.logging", override=True)
load_dotenv(".env.redis", override=True)

# Configuration du logging (doit être fait au début)
from utils.logging_config import setup_logging, get_logger
from utils.logging_middleware import LoggingMiddleware, websocket_logger
from utils.redis_service import redis_service

# Initialiser le système de logging
app_logger = setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_dir=os.getenv("LOG_DIR", "logs"),
    app_name=os.getenv("APP_NAME", "healthy-mcp"),
)

from models import (
    lifespan,
    Session,
    get_session,
    Message,
    Documents,
    Conversation,
    engine,
)

app = FastAPI(lifespan=lifespan)
app.add_middleware(LoggingMiddleware)

# Logger pour ce module
logger = get_logger(__name__)

from streamablehttp_client import StreamableHTTPClient

# Récupération des variables d'environnement
mcp_streaming_url = os.getenv("MCP_STREAMING_HTTP_URL") or ""


async def get_ws_token(
        websocket: WebSocket, token: Annotated[str | None, Query()] = None
):
    if token is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return token


class ConnectionManager:
    def __init__(self, socket: WebSocket):
        self.logger = get_logger("healthy-mcp.websocket.manager")
        self.socket: WebSocket = socket

    async def connect(self):
        await self.socket.accept()
        client_ip = self.socket.client.host if self.socket.client else "Unknown"
        websocket_logger.log_connection(str(id(self.socket)), client_ip)

    async def disconnect(self):
        websocket_id = id(self.socket)
        await self.socket.close()
        websocket_logger.log_disconnection(str(websocket_id))

    async def send_personal_message(self, message: str | dict):
        try:
            data = json.dumps(message) if isinstance(message, dict) else message
            await self.socket.send_text(data)
        except Exception as e:
            raise

    async def send_typing_message(self, status: bool, content: str = ""):
        try:
            await self.socket.send_text(json.dumps({"type": "typing", "status": status, "content": content}))
        except Exception as e:
            raise

    async def send_error_message(self, error: str):
        try:
            await self.socket.send_text(json.dumps({"type": "error", "message": error}))
        except Exception as e:
            raise

    async def broadcast(self, message: str):
        try:
            await self.socket.send_text(message)
        except Exception as e:
            websocket_id = id(self.socket)
            websocket_logger.log_error(str(websocket_id), e)
            await self.disconnect()


# Depends
sessionDep = Annotated[Session, Depends(get_session)]
tokenDep = Annotated[str, Depends(get_ws_token)]


@app.websocket("/ws/{user_id}/conversations/{conversation_id}")
async def conversation_endpoint(websocket: WebSocket, conversation_id: str, token: tokenDep, session: sessionDep):
    ws_logger = get_logger("healthy-mcp.websocket.endpoint")
    manager = ConnectionManager(websocket)
    conversation = session.get(Conversation, conversation_id)

    async def add_message(content: str, role: str = "user", external_id: str | None = None) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            external_id=external_id,
            created_at="now()",  # type: ignore
        )
        session.add(message)
        session.commit()
        return message

    try:
        await manager.connect()
        client = StreamableHTTPClient(token, mcp_streaming_url)
        await client.connect_to_server()

        # Try to get last message from Redis first
        last_message_text: str | None = None
        last_message_text = await redis_service.get_last_message(conversation_id)

        conversation = session.get(Conversation, conversation_id)
        if last_message_text is None:
            last_message = session.exec(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())  # type: ignore
            ).first()
            if last_message:
                last_message_text = last_message.content
                await redis_service.store_last_message(
                    conversation_id, last_message.content
                )

        while True:
            message_received = (await websocket.receive_text()) # format {"message": "text", attachments: [...]}
            try:
                message_data = json.loads(message_received)
            except json.JSONDecodeError as e:
                await manager.send_error_message("Invalid message format")
                continue

            message_content = message_data.get("message", "")
            message_attachments = message_data.get("attachments", [])

            if not message_content or len(message_content.strip()) <= 2:
                await manager.send_error_message("Message content is required")
                continue

            urls = list()  # document URLs extracted from attachments

            await manager.send_typing_message(True, "")
            try:
                message: Message = await add_message(message_content, role="user")
                await manager.send_personal_message({"type": "message-ack", "message": message.dict()})
                # Attachment processing
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

                async for response in client.process_query(message_content, last_message_text, urls):
                    if isinstance(response, TextBlock):
                        message: Message = await add_message(response.text, role="assistant")
                        await manager.send_personal_message({"type": "message-ack", "message": message.dict()})
                        last_message_text = response.text
                        await redis_service.store_last_message(conversation_id, last_message_text)
                    else:
                        ws_logger.warning(f"Unknown response block type: {type(response)}")
                        continue

                await manager.send_typing_message(False, "")

                # generate conversation title
                if (
                    last_message_text
                    and conversation
                    and conversation.title in (None, "", "New Conversation")
                ):
                    conversation_title = await client.process_conversation_title_query(last_message_text)
                    conversation.title = (conversation_title if conversation_title else "New Conversation")
                    conversation.last_message = last_message_text
                    session.add(conversation)
                    session.commit()
                    await manager.send_personal_message({"type": "conversation-ack", "conversation": conversation.dict()})

            except Exception as e:
                ws_logger.error(f"Error processing message: {e}", exc_info=True)
                await manager.send_error_message(str(e))
            finally:
                await manager.send_typing_message(False, "")

    except WebSocketDisconnect:
        ws_logger.info(f"WebSocket disconnected for conversation {conversation_id}")
    except Exception as e:
        ws_logger.error(f"Unexpected error in WebSocket endpoint: {e}", exc_info=True)
    finally:
        if "client" in locals():
            await client.cleanup()


# Routes de santé et d'administration
@app.get("/status/health")
async def health_check():
    """Endpoint de santé pour vérifier l'état du système"""
    health_logger = get_logger("healthy-mcp.health")

    try:
        # Vérifier l'état de Redis
        redis_health = await redis_service.health_check()

        # Vérifier l'état de la base de données
        db_healthy = True
        try:
            with Session(engine) as session:
                session.exec(select(1)).first()
        except Exception as e:
            health_logger.error(f"Database health check failed: {e}")
            db_healthy = False

        health_status = {
            "status": (
                "healthy" if redis_health["connected"] and db_healthy else "degraded"
            ),
            "timestamp": redis_service._get_current_timestamp(),
            "services": {
                "redis": {
                    "status": (
                        "healthy"
                        if redis_health["connected"] and redis_health["ping_successful"]
                        else "unhealthy"
                    ),
                    "connected": redis_health["connected"],
                    "ping_successful": redis_health["ping_successful"],
                    "active_conversations": redis_health["active_conversations"],
                    "error": redis_health.get("error"),
                },
                "database": {"status": "healthy" if db_healthy else "unhealthy"},
            },
        }

        health_logger.info(f"Health check completed: {health_status['status']}")
        return health_status

    except Exception as e:
        health_logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "timestamp": redis_service._get_current_timestamp(),
            "error": str(e),
        }


@app.get("/status/redis-stats")
async def redis_stats(token: Annotated[str, Query()]):
    """Endpoint pour obtenir les statistiques Redis"""
    stats_logger = get_logger("healthy-mcp.redis.stats")

    try:
        active_conversations = await redis_service.get_active_conversations()
        redis_health = await redis_service.health_check()

        stats = {
            "connected": redis_health["connected"],
            "active_conversations": len(active_conversations),
            "conversations": active_conversations[
                :10
            ],  # Limite à 10 pour éviter les réponses trop grandes
            "total_conversations": len(active_conversations),
        }

        stats_logger.debug(
            f"Redis stats requested: {len(active_conversations)} active conversations"
        )
        return stats

    except Exception as e:
        stats_logger.error(f"Failed to get Redis stats: {e}", exc_info=True)
        return {"error": str(e), "connected": False}

async def get_document_by_id(attachment_id: int, session: sessionDep) -> Documents | None:
    db_logger = get_logger("healthy-mcp.database")
    try:
        return session.get(Documents, attachment_id)
    except Exception as e:
        db_logger.error(f"Error fetching document with id {attachment_id}: {e}", exc_info=True)
        return None

async def get_document_download_url(document: Documents, token: str) -> str | None:
    api_logger = get_logger("healthy-mcp.api")
    try:
        api_base_path = os.getenv("API_BASE_URL")
        if not api_base_path:
            return None

        url = (
            f"{api_base_path}/api/documents/{document.id}/download?access_token={token}"
        )
        return url
    except Exception as e:
        api_logger.error(
            f"Error generating download URL for document {document.id}: {e}"
        )
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
