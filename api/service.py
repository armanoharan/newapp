"""Business logic shared by the REST API and the MCP server.

Functions take already-validated data and return plain dicts. They raise
NotFound / Conflict / Invalid, which each interface maps to its own errors.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select

from .db import CompanyRow, ContactRow, DealRow, session_scope

STAGES = ["prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"]
OPEN_STAGES = {"prospecting", "qualification", "proposal", "negotiation"}


class ServiceError(Exception):
    pass


class NotFound(ServiceError):
    pass


class Conflict(ServiceError):
    pass


class Invalid(ServiceError):
    pass


def _like(column, text: str):
    return column.ilike(f"%{text}%")


def _get(session, model, item_id: int, kind: str):
    row = session.get(model, item_id)
    if row is None:
        raise NotFound(f"{kind} {item_id} not found")
    return row


def _check_company(session, company_id: int) -> None:
    if session.get(CompanyRow, company_id) is None:
        raise Invalid(f"company_id {company_id} does not exist")


def _check_contact(session, contact_id: int | None, company_id: int) -> None:
    if contact_id is None:
        return
    contact = session.get(ContactRow, contact_id)
    if contact is None:
        raise Invalid(f"contact_id {contact_id} does not exist")
    if contact.company_id != company_id:
        raise Invalid(f"contact {contact_id} does not belong to company {company_id}")


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
def list_companies(q=None, industry=None, country=None, min_employees=None, limit=100, offset=0) -> list[dict]:
    stmt = select(CompanyRow).order_by(CompanyRow.id)
    if q:
        stmt = stmt.where(or_(_like(CompanyRow.name, q), _like(CompanyRow.domain, q),
                              _like(CompanyRow.description, q)))
    if industry:
        stmt = stmt.where(_like(CompanyRow.industry, industry))
    if country:
        stmt = stmt.where(func.lower(CompanyRow.country) == country.lower())
    if min_employees is not None:
        stmt = stmt.where(CompanyRow.employees >= min_employees)
    with session_scope() as s:
        return [r.to_dict() for r in s.scalars(stmt.limit(limit).offset(offset))]


def get_company(company_id: int) -> dict:
    with session_scope() as s:
        return _get(s, CompanyRow, company_id, "Company").to_dict()


def create_company(data: dict[str, Any]) -> dict:
    with session_scope() as s:
        row = CompanyRow(**data)
        s.add(row)
        s.flush()
        return row.to_dict()


def update_company(company_id: int, changes: dict[str, Any]) -> dict:
    with session_scope() as s:
        row = _get(s, CompanyRow, company_id, "Company")
        for k, v in changes.items():
            setattr(row, k, v)
        s.flush()
        return row.to_dict()


def delete_company(company_id: int, cascade: bool = False) -> None:
    with session_scope() as s:
        row = _get(s, CompanyRow, company_id, "Company")
        contacts = s.scalars(select(ContactRow).where(ContactRow.company_id == company_id)).all()
        deals = s.scalars(select(DealRow).where(DealRow.company_id == company_id)).all()
        if (contacts or deals) and not cascade:
            raise Conflict(f"Company has {len(contacts)} contacts and {len(deals)} deals; "
                           "pass cascade=true to delete them too")
        for d in deals:
            s.delete(d)
        s.flush()
        for c in contacts:
            s.delete(c)
        s.flush()
        s.delete(row)


def company_contacts(company_id: int) -> list[dict]:
    get_company(company_id)
    return list_contacts(company_id=company_id, limit=10_000)


def company_deals(company_id: int) -> list[dict]:
    get_company(company_id)
    return list_deals(company_id=company_id, limit=10_000)


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #
def list_contacts(q=None, company_id=None, title=None, limit=100, offset=0) -> list[dict]:
    stmt = select(ContactRow).order_by(ContactRow.id)
    if q:
        full_name = ContactRow.first_name + " " + ContactRow.last_name
        stmt = stmt.where(or_(_like(full_name, q), _like(ContactRow.email, q), _like(ContactRow.title, q)))
    if company_id is not None:
        stmt = stmt.where(ContactRow.company_id == company_id)
    if title:
        stmt = stmt.where(_like(ContactRow.title, title))
    with session_scope() as s:
        return [r.to_dict() for r in s.scalars(stmt.limit(limit).offset(offset))]


def get_contact(contact_id: int) -> dict:
    with session_scope() as s:
        return _get(s, ContactRow, contact_id, "Contact").to_dict()


def create_contact(data: dict[str, Any]) -> dict:
    with session_scope() as s:
        _check_company(s, data["company_id"])
        row = ContactRow(**data)
        s.add(row)
        s.flush()
        return row.to_dict()


def update_contact(contact_id: int, changes: dict[str, Any]) -> dict:
    with session_scope() as s:
        row = _get(s, ContactRow, contact_id, "Contact")
        if "company_id" in changes:
            _check_company(s, changes["company_id"])
        for k, v in changes.items():
            setattr(row, k, v)
        s.flush()
        return row.to_dict()


def delete_contact(contact_id: int) -> None:
    """Delete a contact; deals that referenced it keep existing with contact_id cleared."""
    with session_scope() as s:
        row = _get(s, ContactRow, contact_id, "Contact")
        for d in s.scalars(select(DealRow).where(DealRow.contact_id == contact_id)):
            d.contact_id = None
        s.flush()
        s.delete(row)


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
def list_deals(q=None, company_id=None, contact_id=None, stage=None, owner=None, min_amount=None,
               max_amount=None, closing_before: date | None = None, closing_after: date | None = None,
               limit=100, offset=0) -> list[dict]:
    stmt = select(DealRow).order_by(DealRow.id)
    if q:
        stmt = stmt.where(or_(_like(DealRow.name, q), _like(DealRow.product, q)))
    if company_id is not None:
        stmt = stmt.where(DealRow.company_id == company_id)
    if contact_id is not None:
        stmt = stmt.where(DealRow.contact_id == contact_id)
    if stage:
        stmt = stmt.where(DealRow.stage == stage)
    if owner:
        stmt = stmt.where(func.lower(DealRow.owner) == owner.lower())
    if min_amount is not None:
        stmt = stmt.where(DealRow.amount_usd >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(DealRow.amount_usd <= max_amount)
    if closing_before is not None:
        stmt = stmt.where(DealRow.close_date <= closing_before)
    if closing_after is not None:
        stmt = stmt.where(DealRow.close_date >= closing_after)
    with session_scope() as s:
        return [r.to_dict() for r in s.scalars(stmt.limit(limit).offset(offset))]


def get_deal(deal_id: int) -> dict:
    with session_scope() as s:
        return _get(s, DealRow, deal_id, "Deal").to_dict()


def create_deal(data: dict[str, Any]) -> dict:
    with session_scope() as s:
        _check_company(s, data["company_id"])
        _check_contact(s, data.get("contact_id"), data["company_id"])
        row = DealRow(**data)
        s.add(row)
        s.flush()
        return row.to_dict()


def update_deal(deal_id: int, changes: dict[str, Any]) -> dict:
    with session_scope() as s:
        row = _get(s, DealRow, deal_id, "Deal")
        company_id = changes.get("company_id", row.company_id)
        if "company_id" in changes:
            _check_company(s, company_id)
        _check_contact(s, changes.get("contact_id", row.contact_id), company_id)
        # Keep probability consistent with terminal stages unless explicitly set.
        if "probability" not in changes and changes.get("stage") in ("closed_won", "closed_lost"):
            changes["probability"] = 100 if changes["stage"] == "closed_won" else 0
        for k, v in changes.items():
            setattr(row, k, v)
        s.flush()
        return row.to_dict()


def delete_deal(deal_id: int) -> None:
    with session_scope() as s:
        s.delete(_get(s, DealRow, deal_id, "Deal"))


def pipeline_summary(owner: str | None = None) -> dict:
    stmt = select(DealRow)
    if owner:
        stmt = stmt.where(func.lower(DealRow.owner) == owner.lower())
    with session_scope() as s:
        rows = [r.to_dict() for r in s.scalars(stmt)]
    stages = []
    for stage in STAGES:
        in_stage = [d for d in rows if d["stage"] == stage]
        stages.append({
            "stage": stage,
            "count": len(in_stage),
            "total_amount_usd": sum(d["amount_usd"] for d in in_stage),
            "weighted_amount_usd": sum(d["amount_usd"] * d["probability"] // 100 for d in in_stage),
        })
    open_stages = [st for st in stages if st["stage"] in OPEN_STAGES]
    return {
        "total_deals": len(rows),
        "open_pipeline_usd": sum(st["total_amount_usd"] for st in open_stages),
        "weighted_pipeline_usd": sum(st["weighted_amount_usd"] for st in open_stages),
        "won_usd": next(st["total_amount_usd"] for st in stages if st["stage"] == "closed_won"),
        "stages": stages,
    }
