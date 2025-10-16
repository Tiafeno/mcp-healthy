from sqlmodel import Field, SQLModel

class Documents(SQLModel, table=True):
    __tablename__ = "documents"

    id: int = Field(default=None, primary_key=True)
    message_uuid: str | None = Field(default=None, foreign_key="ai_conversation_messages.uuid")
    name: str
    path: str
    mime_type: str
    size: int
    created_at: str = Field()
    updated_at: str | None = None