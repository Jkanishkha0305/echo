from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .models import UserLog  # adjust import based on your structure

def create_or_update_log(db: Session, user_id: str, chat_id: str, message: str):
    message = message.strip()
    if not message:
        return

    # Fetch the latest log entry for this user/chat
    last_log = (
        db.query(UserLog)
        .filter_by(user_id=user_id, chat_id=chat_id)
        .order_by(desc(UserLog.created_at))
        .first()
    )

    # Avoid logging duplicates
    if last_log and last_log.message.strip() == message:
        return

    # Create new log
    new_log = UserLog(
        user_id=user_id,
        chat_id=chat_id,
        message=message,
        created_at=datetime.utcnow()
    )
    db.add(new_log)
    db.commit()
