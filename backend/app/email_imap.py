from __future__ import annotations

import imaplib
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.queueing import dispatch_document_job
from app.services.email_intake import EmailIntakeError, EmailIntakeService

logger = logging.getLogger(__name__)


def poll_imap_once(
    *,
    settings: Settings | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    imap_factory: Callable[..., imaplib.IMAP4] | None = None,
) -> int:
    active_settings = settings or get_settings()
    if not active_settings.email_imap_enabled:
        return 0
    if not (
        active_settings.email_imap_host
        and active_settings.email_imap_username
        and active_settings.email_imap_password.get_secret_value()
    ):
        raise RuntimeError("Az IMAP worker engedélyezett, de a kapcsolat nincs konfigurálva.")

    factory = imap_factory
    if factory is None:
        factory = (
            imaplib.IMAP4_SSL
            if active_settings.email_imap_use_ssl
            else imaplib.IMAP4
        )
    client = factory(
        active_settings.email_imap_host,
        active_settings.email_imap_port,
    )
    processed = 0
    try:
        client.login(
            active_settings.email_imap_username,
            active_settings.email_imap_password.get_secret_value(),
        )
        status, _ = client.select(active_settings.email_imap_mailbox)
        if status != "OK":
            raise RuntimeError("Az IMAP postafiók nem nyitható meg.")
        status, payload = client.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("Az IMAP keresés sikertelen.")
        uids = payload[0].split() if payload and payload[0] else []
        for uid in uids:
            status, fetched = client.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            raw_message = next(
                (
                    item[1]
                    for item in fetched
                    if isinstance(item, tuple)
                    and len(item) > 1
                    and isinstance(item[1], bytes)
                ),
                None,
            )
            if raw_message is None:
                continue
            uid_text = uid.decode("ascii", errors="ignore")
            mark_seen = False
            try:
                with session_factory() as session:
                    result = EmailIntakeService(
                        session, settings=active_settings
                    ).ingest_raw(
                        raw_message,
                        provider="imap",
                        provider_message_id=(
                            f"{active_settings.email_imap_username}:"
                            f"{active_settings.email_imap_mailbox}:{uid_text}"
                        ),
                        correlation_id=f"imap:{uid_text}",
                    )
                    for job_id in result.job_ids:
                        dispatch_document_job(job_id)
                processed += 1
                mark_seen = True
            except EmailIntakeError as exc:
                logger.warning("Az IMAP-levél elutasítva (%s): %s", uid_text, exc.code)
                mark_seen = True
            except Exception:
                logger.exception("Az IMAP-levél feldolgozása sikertelen: %s", uid_text)
            if mark_seen:
                client.uid("store", uid, "+FLAGS", "(\\Seen)")
        return processed
    finally:
        try:
            client.logout()
        except Exception:
            logger.debug("Az IMAP kapcsolat lezárása nem sikerült.", exc_info=True)
