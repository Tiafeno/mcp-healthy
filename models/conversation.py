from sqlmodel import Field, SQLModel
from sqlalchemy import event
from datetime import datetime
import uuid

class Conversation(SQLModel, table=True):
    __tablename__ = "ai_conversations"
    
    uuid: str | None = Field(default=None, primary_key=True)
    user_id: str
    last_message: str|None = None
    last_message_role: str|None = None
    created_at: str
    updated_at: str | None = None
    deleted_at: str | None = None
    
class Message(SQLModel, table=True):
    __tablename__ = "ai_conversation_messages"
    
    uuid: str | None = Field(default=None, primary_key=True)
    conversation_id: str
    role: str
    content: str
    created_at: datetime = Field()
    updated_at: datetime | None = None
    
    def dict(self):
        return {
            "uuid": self.uuid.__str__(),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }

@event.listens_for(Conversation, "before_insert")
@event.listens_for(Message, "before_insert")
def set_conversation_uuid(mapper, connection, target):
    if target.uuid is None:
        target.uuid = uuid.uuid4().__str__()