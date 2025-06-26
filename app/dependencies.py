from fastapi import Request, Cookie, Depends
from typing import Optional
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from .database import get_db
from .auth import SECRET_KEY, ALGORITHM
from . import models

async def get_current_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            return None

        db = next(get_db())
        user = db.query(models.User).filter(models.User.email == email).first()
        return user

    except jwt.ExpiredSignatureError:
        return None
    except JWTError:
        return None

async def get_current_user_for_templates(
    request: Request,
    user = Depends(get_current_user_from_cookie)
):
    """For templates, return whether user is logged in and the user's name"""
    if user:
        return {
            "user_logged_in": True,
            "user_name": user.name,
            "user_id": user.id
        }
    return {
        "user_logged_in": False,
        "user_name": None,
        "user_id": None
    }