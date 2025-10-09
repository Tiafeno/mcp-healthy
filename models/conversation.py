from sqlmodel import Field, SQLModel

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
    created_at: str
    updated_at: str | None = None