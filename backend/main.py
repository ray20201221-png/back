from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai import ask_ai
from auth import create_token, decode_token, hash_password, verify_password
from database import SessionLocal, engine
from models import Base, Message, User


Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_DIR = Path(__file__).resolve().parent
READABLE_CODE_EXTENSIONS = {".py", ".txt"}
user_histories = {}


def ensure_columns():
    with engine.connect() as conn:
        columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if "is_admin" not in columns:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
        conn.commit()


ensure_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str


def current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "", 1)
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == payload.get("username")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def admin_user(user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


@app.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if user:
        return {"success": False, "message": "帳號已存在"}

    new_user = User(
        username=req.username,
        password=hash_password(req.password),
        is_admin=False,
    )

    db.add(new_user)
    db.commit()

    return {"success": True}


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
        "username": user.username,
        "is_admin": bool(user.is_admin),
    }


@app.post("/chat")
def chat(
    req: ChatRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    session = user_histories.get(user.username, [])

    session.append({"role": "user", "content": req.message})
    db.add(Message(role="user", content=req.message, user_id=user.id))

    messages = [
        {
            "role": "system",
            "content": "你是 RUI AI，請用清楚、友善的繁體中文回答。",
        },
        *session[-20:],
    ]

    reply = ask_ai(messages)

    session.append({"role": "assistant", "content": reply})
    db.add(Message(role="assistant", content=reply, user_id=user.id))
    db.commit()

    user_histories[user.username] = session

    return {"reply": reply}


@app.post("/clear")
def clear(user: User = Depends(current_user)):
    user_histories[user.username] = []
    return {"message": "cleared"}


@app.get("/admin/users")
def admin_users(
    _: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.id).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "is_admin": bool(user.is_admin),
        }
        for user in users
    ]


@app.get("/admin/users/{user_id}/messages")
def admin_user_messages(
    user_id: int,
    _: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    messages = (
        db.query(Message)
        .filter(Message.user_id == user_id)
        .order_by(Message.id)
        .all()
    )

    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
        }
        for message in messages
    ]


@app.get("/admin/code")
def admin_code_files(_: User = Depends(admin_user)):
    return [
        path.name
        for path in sorted(BACKEND_DIR.iterdir())
        if path.is_file() and path.suffix in READABLE_CODE_EXTENSIONS
    ]


@app.get("/admin/code/{filename}")
def admin_code_file(filename: str, _: User = Depends(admin_user)):
    path = (BACKEND_DIR / filename).resolve()

    if path.parent != BACKEND_DIR or path.suffix not in READABLE_CODE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file")

    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "filename": path.name,
        "content": path.read_text(encoding="utf-8"),
    }
