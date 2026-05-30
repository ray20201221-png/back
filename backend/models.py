from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from datetime import datetime
from database import Base

class User(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    username = Column(String, unique=True)

    password = Column(String)

    is_admin = Column(Boolean, default=False)


class Message(Base):

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)

    role = Column(String)

    content = Column(Text)

    user_id = Column(Integer, ForeignKey("users.id"))

    conversation_id = Column(Integer, ForeignKey("conversations.id"))


class Conversation(Base):

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"))

    title = Column(String, default="New chat")

    created_at = Column(DateTime, default=datetime.utcnow)
