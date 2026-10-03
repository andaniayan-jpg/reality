"""Persistent, atomic AI request reservations and coarse usage accounting."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from .database import AIDailyUsage


class AIQuotaExceeded(RuntimeError):
    """The account's UTC-day AI request allowance is exhausted."""


def current_day() -> str:
    return datetime.now(UTC).date().isoformat()


def reserve_ai_request(
    session: Session,
    *,
    owner_id: str,
    limit: int,
    prompt_chars: int,
    image_bytes: int,
) -> str:
    """Reserve one request with a single conditional database UPDATE.

    The insert and update run in one transaction; PostgreSQL row locking
    serializes concurrent reservations across API replicas.
    """
    day = current_day()
    session.execute(
        text(
            "INSERT INTO ai_daily_usage "
            "(owner_id, day, request_count, prompt_chars, image_bytes, output_chars) "
            "VALUES (:owner_id, :day, 0, 0, 0, 0) "
            "ON CONFLICT (owner_id, day) DO NOTHING"
        ),
        {"owner_id": owner_id, "day": day},
    )
    changed = session.execute(
        update(AIDailyUsage)
        .where(
            AIDailyUsage.owner_id == owner_id,
            AIDailyUsage.day == day,
            AIDailyUsage.request_count < limit,
        )
        .values(
            request_count=AIDailyUsage.request_count + 1,
            prompt_chars=AIDailyUsage.prompt_chars + prompt_chars,
            image_bytes=AIDailyUsage.image_bytes + image_bytes,
        )
    ).rowcount
    if changed != 1:
        session.rollback()
        raise AIQuotaExceeded("daily AI request allowance exhausted")
    session.commit()
    return day


def record_ai_output(session: Session, *, owner_id: str, day: str, chars: int) -> None:
    session.execute(
        update(AIDailyUsage)
        .where(AIDailyUsage.owner_id == owner_id, AIDailyUsage.day == day)
        .values(output_chars=AIDailyUsage.output_chars + chars)
    )
    session.commit()
