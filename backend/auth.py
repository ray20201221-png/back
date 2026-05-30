import hashlib
import jwt
import datetime

# ⚠️ 你可以自己改這個密鑰（很重要）
SECRET_KEY = "rui-ai-secret-key"
ALGORITHM = "HS256"


# =========================
# 密碼加密（SHA256）
# =========================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# =========================
# 密碼驗證
# =========================
def verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("$2"):
        try:
            import bcrypt

            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    return hashlib.sha256(password.encode("utf-8")).hexdigest() == hashed


# =========================
# 建立 Token（JWT）
# =========================
def create_token(data: dict):
    payload = data.copy()

    payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(days=7)

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return token


# =========================
# 解碼 Token（未來可用）
# =========================
def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        return None
