from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai import ask_ai
from auth import create_token, decode_token, hash_password, verify_password
from database import SessionLocal, engine
from models import Base, Conversation, Message, User
from rag import KNOWLEDGE_DIR, MIN_CONFIDENCE, rag_context, rebuild_index


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
READABLE_CODE_EXTENSIONS = {".py", ".txt", ".md"}
user_histories = {}
active_conversations = {}
MEMORY_LIMIT = 20
SMALL_TALK = {
    "hi",
    "hello",
    "hey",
    "你好",
    "嗨",
    "哈囉",
    "謝謝",
    "thanks",
    "thank you",
}


def ensure_columns():
    with engine.connect() as conn:
        user_columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if "is_admin" not in user_columns:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")

        message_columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(messages)").fetchall()]
        if "conversation_id" not in message_columns:
            conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN conversation_id INTEGER")
        conn.commit()


def ensure_admin_user():
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").first()
        if admin:
            admin.is_admin = True
            if not admin.password:
                admin.password = hash_password("admin")
        else:
            db.add(
                User(
                    username="admin",
                    password=hash_password("admin"),
                    is_admin=True,
                )
            )
        db.commit()


ensure_columns()
ensure_admin_user()


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


def load_user_memory(user: User, db: Session):
    conversation = get_active_conversation(user, db)
    key = (user.id, conversation.id)
    if key in user_histories:
        return user_histories[key]

    stored_messages = (
        db.query(Message)
        .filter(Message.user_id == user.id)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(MEMORY_LIMIT)
        .all()
    )

    session = [
        {"role": message.role, "content": message.content}
        for message in reversed(stored_messages)
    ]
    user_histories[key] = session
    return session


def migrate_legacy_conversation(user: User, db: Session):
    legacy_messages = (
        db.query(Message)
        .filter(Message.user_id == user.id)
        .filter(Message.conversation_id.is_(None))
        .order_by(Message.id)
        .all()
    )
    if not legacy_messages:
        return None

    title = legacy_messages[0].content[:30] or "Previous chat"
    conversation = Conversation(user_id=user.id, title=title)
    db.add(conversation)
    db.flush()

    for message in legacy_messages:
        message.conversation_id = conversation.id

    db.commit()
    return conversation


def get_active_conversation(user: User, db: Session):
    if user.id in active_conversations:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == active_conversations[user.id])
            .filter(Conversation.user_id == user.id)
            .first()
        )
        if conversation:
            return conversation

    legacy = migrate_legacy_conversation(user, db)
    conversation = legacy or (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.id.desc())
        .first()
    )

    if not conversation:
        conversation = Conversation(user_id=user.id, title="New chat")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    active_conversations[user.id] = conversation.id
    return conversation


def serialize_message(message: Message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
    }


def should_enforce_rag_threshold(message: str):
    normalized = message.strip().lower()
    if normalized in SMALL_TALK:
        return False
    return True


def low_confidence_reply(rag: dict):
    return (
        "我目前沒有足夠可靠的知識庫資料可以回答這個問題，所以先不硬猜。\n\n"
        f"目前信心分數：{rag['confidence']}\n"
        f"門檻分數：{rag['min_confidence']}\n\n"
        "你可以把相關資料放進 `backend/knowledge/`，或換一個更具體的問法。"
    )


@app.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if user:
        return {"success": False, "message": "Username already exists"}

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
        return {"success": False, "message": "Username not found"}

    if not verify_password(req.password, user.password):
        return {"success": False, "message": "Wrong password"}

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
    conversation = get_active_conversation(user, db)
    session = load_user_memory(user, db)

    session.append({"role": "user", "content": req.message})
    if conversation.title == "New chat":
        conversation.title = req.message[:30]
    db.add(Message(role="user", content=req.message, user_id=user.id, conversation_id=conversation.id))

    rag = rag_context(req.message)
    if should_enforce_rag_threshold(req.message) and not rag["passed"]:
        reply = low_confidence_reply(rag)
        session.append({"role": "assistant", "content": reply})
        db.add(Message(role="assistant", content=reply, user_id=user.id, conversation_id=conversation.id))
        db.commit()
        user_histories[(user.id, conversation.id)] = session
        return {
            "reply": reply,
            "sources": rag["sources"],
            "confidence": rag["confidence"],
            "min_confidence": rag["min_confidence"],
            "refused": True,
            "conversation_id": conversation.id,
        }

    system_prompt = """
You are RUI AI. Answer clearly and kindly in Traditional Chinese.
If RAG context is available, use it as the primary source.
If the context is insufficient, say what is missing and then provide a careful general answer.
""".strip()

    if rag["context"]:
        system_prompt += f"\n\nRAG context:\n{rag['context']}"

    messages = [
        {"role": "system", "content": system_prompt},
        *session[-MEMORY_LIMIT:],
    ]

    reply = ask_ai(messages)

    if rag["sources"]:
        source_text = "\n".join(
            f"- {source['source']}#{source['chunk']}"
            for source in rag["sources"]
        )
        reply = f"{reply}\n\nSources:\n{source_text}"

    session.append({"role": "assistant", "content": reply})
    db.add(Message(role="assistant", content=reply, user_id=user.id, conversation_id=conversation.id))
    db.commit()

    user_histories[(user.id, conversation.id)] = session

    return {
        "reply": reply,
        "sources": rag["sources"],
        "confidence": rag["confidence"],
        "min_confidence": rag["min_confidence"],
        "refused": False,
        "conversation_id": conversation.id,
    }


@app.post("/clear")
def clear(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conversation = Conversation(user_id=user.id, title="New chat")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    active_conversations[user.id] = conversation.id
    user_histories[(user.id, conversation.id)] = []
    return {"message": "cleared", "conversation_id": conversation.id}


@app.get("/conversations")
def conversations(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    migrate_legacy_conversation(user, db)
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.id.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "title": row.title or "New chat",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "active": active_conversations.get(user.id) == row.id,
        }
        for row in rows
    ]


@app.get("/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id)
        .filter(Conversation.user_id == user.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    active_conversations[user.id] = conversation.id

    messages = (
        db.query(Message)
        .filter(Message.user_id == user.id)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.id)
        .all()
    )
    user_histories[(user.id, conversation.id)] = [
        {"role": message.role, "content": message.content}
        for message in messages[-MEMORY_LIMIT:]
    ]
    return [serialize_message(message) for message in messages]


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


@app.get("/admin/rag/status")
def admin_rag_status(_: User = Depends(admin_user)):
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    files = [
        str(path.relative_to(KNOWLEDGE_DIR))
        for path in sorted(KNOWLEDGE_DIR.rglob("*"))
        if path.is_file()
    ]
    return {
        "knowledge_dir": str(KNOWLEDGE_DIR),
        "files": files,
        "file_count": len(files),
        "min_confidence": MIN_CONFIDENCE,
    }


@app.post("/admin/rag/reindex")
def admin_rag_reindex(_: User = Depends(admin_user)):
    rebuild_index(force=True)
    return {"success": True, "message": "RAG index rebuilt"}
