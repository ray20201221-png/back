from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Base, User
from auth import hash_password, verify_password, create_token
from ai import ask_ai

# 建立資料表
Base.metadata.create_all(bind=engine)

app = FastAPI()

# =====================
# CORS（一定要）
# =====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================
# DB Dependency（修正重點）
# =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
# AI Memory（簡化版）
# =====================
user_histories = {}

# =====================
# Register
# =====================
@app.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.username == req.username).first()

    if user:
        return {"success": False, "message": "帳號已存在"}

    new_user = User(
        username=req.username,
        password=hash_password(req.password)
    )

    db.add(new_user)
    db.commit()

    return {"success": True}

# =====================
# Login
# =====================
@app.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.username == req.username).first()

    if not user:
        return {"success": False, "message": "帳號不存在"}

    if not verify_password(req.password, user.password):
        return {"success": False, "message": "密碼錯誤"}

    token = create_token({"username": user.username})

    return {
        "success": True,
        "token": token,
        "username": user.username
    }

# =====================
# Chat（修正版）
# =====================
@app.post("/chat")
def chat(req: ChatRequest):

    session = user_histories.get("default", [])

    session.append({
        "role": "user",
        "content": req.message
    })

    messages = [
        {
            "role": "system",
            "content": "你是 RUI AI，請用自然方式回答使用者。"
        },
        *session[-20:]
    ]

    reply = ask_ai(messages)

    session.append({
        "role": "assistant",
        "content": reply
    })

    user_histories["default"] = session

    return {"reply": reply}

# =====================
# Clear Chat
# =====================
@app.post("/clear")
def clear():

    user_histories["default"] = []

    return {"message": "cleared"}
