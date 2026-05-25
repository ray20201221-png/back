from jose import jwt
from passlib.context import CryptContext

SECRET_KEY = "RUI_SECRET"

ALGORITHM = "HS256"

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

def hash_password(password):

    return pwd_context.hash(password)

def verify_password(password, hashed):

    return pwd_context.verify(password, hashed)

def create_token(data):

    return jwt.encode(
        data,
        SECRET_KEY,
        algorithm=ALGORITHM
    )