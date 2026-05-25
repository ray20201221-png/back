from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Base, User
from auth import (
    hash_password,
    verify_password,
    create_token
)

from ai import ask_ai

# 建立資料表
Base.metadata.create_all(bind=engine)

app = FastAPI()

db: Session = SessionLocal()

# =====================
# Request Models
# =====================

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str

# =====================
# AI 記憶
# =====================

chat_history = []

# =====================
# Register
# =====================

@app.post("/register")
def register(req: RegisterRequest):

    user = db.query(User).filter(
        User.username == req.username
    ).first()

    if user:

        return {
            "success": False,
            "message": "帳號已存在"
        }

    new_user = User(
        username=req.username,
        password=hash_password(req.password)
    )

    db.add(new_user)

    db.commit()

    return {
        "success": True
    }

# =====================
# Login
# =====================

@app.post("/login")
def login(req: LoginRequest):

    user = db.query(User).filter(
        User.username == req.username
    ).first()

    if not user:

        return {
            "success": False,
            "message": "帳號不存在"
        }

    if not verify_password(
        req.password,
        user.password
    ):

        return {
            "success": False,
            "message": "密碼錯誤"
        }

    token = create_token({
        "username": user.username
    })

    return {
        "success": True,
        "token": token,
        "username": user.username
    }

# =====================
# Chat
# =====================

@app.post("/chat")
def chat(req: ChatRequest):

    global chat_history

    chat_history.append({
        "role": "user",
        "content": req.message
    })

    messages = [

        {
            "role": "system",
            "content": """
你是 RUI AI。

規則：

1. 使用使用者語言
2. 不要混合語言
3. 像 ChatGPT 一樣
4. 保持自然聊天
"""
        },

        *chat_history[-20:]
    ]

    reply = ask_ai(messages)

    chat_history.append({
        "role": "assistant",
        "content": reply
    })

    return {
        "reply": reply
    }

# =====================
# Clear Memory
# =====================

@app.post("/clear")
def clear():

    global chat_history

    chat_history = []

    return {
        "message": "cleared"
    }

# =====================
# Frontend
# =====================

app.mount(
    "/",
    StaticFiles(directory="../frontend", html=True),
    name="frontend"
)