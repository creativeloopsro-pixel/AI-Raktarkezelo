from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models import Organization, Product, StockBalance, User
from app.security import hash_password


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session(session_factory) -> Generator[Session, None, None]:
    with session_factory() as database_session:
        yield database_session


@pytest.fixture
def seeded(session: Session) -> tuple[Organization, User, Product]:
    organization = Organization(name="Tesztbolt", slug="tesztbolt")
    session.add(organization)
    session.flush()
    user = User(
        organization_id=organization.id,
        email="admin@teszt.hu",
        full_name="Teszt Admin",
        password_hash=hash_password("Secret-1234!"),
        role="admin",
    )
    product = Product(
        organization_id=organization.id,
        name="Teszt termék",
        internal_sku="TEST-001",
        min_stock=5,
    )
    session.add_all([user, product])
    session.flush()
    session.add(
        StockBalance(
            organization_id=organization.id,
            product_id=product.id,
        )
    )
    session.commit()
    return organization, user, product


@pytest.fixture
def client(session_factory, seeded) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_database():
        with session_factory() as database_session:
            try:
                yield database_session
            finally:
                database_session.close()

    app.dependency_overrides[get_db] = override_database
    with TestClient(app) as test_client:
        yield test_client
