"""Database setup. Uses DATABASE_URL (Postgres in production), falling back to a local SQLite file."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date
from typing import Iterator

from sqlalchemy import Date, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from . import seed_data


def _normalize_url(url: str) -> str:
    # Render/Heroku-style URLs use postgres:// - point SQLAlchemy at the psycopg 3 driver.
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _make_engine(url: str) -> Engine:
    url = _normalize_url(url)
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


engine: Engine = _make_engine(os.environ.get("DATABASE_URL", "sqlite:///./crm.db"))
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class CompanyRow(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(200))
    employees: Mapped[int] = mapped_column(Integer)
    annual_revenue_usd: Mapped[int] = mapped_column(Integer)
    hq_city: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")


class ContactRow(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(60), default="")
    title: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)


class DealRow(Base):
    __tablename__ = "deals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    amount_usd: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(40), index=True)
    probability: Mapped[int] = mapped_column(Integer)
    close_date: Mapped[date] = mapped_column(Date)
    owner: Mapped[str] = mapped_column(String(120))
    product: Mapped[str] = mapped_column(String(200))


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _seed(session: Session) -> None:
    """Insert the sample data, letting the database assign ids (keeps Postgres sequences correct)."""
    company_ids: dict[int, int] = {}
    for c in seed_data.COMPANIES:
        row = CompanyRow(**{k: v for k, v in c.items() if k != "id"})
        session.add(row)
        session.flush()
        company_ids[c["id"]] = row.id

    contact_ids: dict[int, int] = {}
    for c in seed_data.CONTACTS:
        data = {k: v for k, v in c.items() if k != "id"}
        data["company_id"] = company_ids[c["company_id"]]
        row = ContactRow(**data)
        session.add(row)
        session.flush()
        contact_ids[c["id"]] = row.id

    for d in seed_data.DEALS:
        data = {k: v for k, v in d.items() if k != "id"}
        data["company_id"] = company_ids[d["company_id"]]
        data["contact_id"] = contact_ids.get(d["contact_id"]) if d["contact_id"] else None
        data["close_date"] = date.fromisoformat(d["close_date"])
        session.add(DealRow(**data))


def init_db() -> None:
    """Create tables and load sample data if the database is empty."""
    Base.metadata.create_all(engine)
    with session_scope() as session:
        if session.scalar(select(CompanyRow.id).limit(1)) is None:
            _seed(session)


def reset_db() -> None:
    """Drop everything and reload the sample data (used by tests)."""
    Base.metadata.drop_all(engine)
    init_db()
