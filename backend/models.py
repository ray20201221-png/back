from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
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
