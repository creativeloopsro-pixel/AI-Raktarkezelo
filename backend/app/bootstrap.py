from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import EmailInboundSettings, Organization, User
from app.security import hash_password
from app.services.plugins import PluginService


def bootstrap() -> None:
    settings = get_settings()
    with SessionLocal.begin() as session:
        organization = session.scalar(
            select(Organization).where(Organization.slug == settings.bootstrap_organization_slug)
        )
        if organization is None:
            organization = Organization(
                name=settings.bootstrap_organization,
                slug=settings.bootstrap_organization_slug,
            )
            session.add(organization)
            session.flush()

        admin = session.scalar(
            select(User).where(
                User.organization_id == organization.id,
                User.email == settings.bootstrap_admin_email.lower(),
            )
        )
        if admin is None:
            session.add(
                User(
                    organization_id=organization.id,
                    email=settings.bootstrap_admin_email.lower(),
                    full_name="Rendszergazda",
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role="admin",
                )
            )
        inbound = session.get(EmailInboundSettings, organization.id)
        if inbound is None:
            session.add(EmailInboundSettings(organization_id=organization.id))
    with SessionLocal() as session:
        PluginService(session).ensure_all_builtin_plugins()


if __name__ == "__main__":
    bootstrap()
