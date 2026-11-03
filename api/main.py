"""FastAPI application exposing REST APIs for Companies, Contacts and Deals."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, FastAPI, HTTPException, Query, Response

from .models import (
    Company, CompanyCreate, CompanyUpdate,
    Contact, ContactCreate, ContactUpdate,
    Deal, DealCreate, DealStage, DealUpdate,
    PipelineStage, PipelineSummary,
)
from .store import store

app = FastAPI(
    title="B2B CRM API",
    version="1.0.0",
    description="Companies, Contacts and Deals for a B2B software sales team.",
)


def _not_found(kind: str, item_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{kind} {item_id} not found")


def _require_company(company_id: int) -> None:
    if store.companies.get(company_id) is None:
        raise HTTPException(status_code=422, detail=f"company_id {company_id} does not exist")


def _require_contact(contact_id: int | None, company_id: int | None = None) -> None:
    if contact_id is None:
        return
    contact = store.contacts.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=422, detail=f"contact_id {contact_id} does not exist")
    if company_id is not None and contact["company_id"] != company_id:
        raise HTTPException(
            status_code=422,
            detail=f"contact {contact_id} does not belong to company {company_id}",
        )


def _contains(haystack: str, needle: str | None) -> bool:
    return needle is None or needle.lower() in haystack.lower()


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"service": "b2b-crm", "docs": "/docs", "resources": ["/companies", "/contacts", "/deals"]}


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
companies = APIRouter(prefix="/companies", tags=["companies"])


@companies.get("", response_model=list[Company])
def list_companies(
    q: str | None = Query(None, description="Search name, domain or description"),
    industry: str | None = None,
    country: str | None = None,
    min_employees: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = [
        c for c in store.companies.all()
        if (q is None or any(_contains(c[f], q) for f in ("name", "domain", "description")))
        and _contains(c["industry"], industry)
        and (country is None or c["country"].lower() == country.lower())
        and (min_employees is None or c["employees"] >= min_employees)
    ]
    return rows[offset: offset + limit]


@companies.get("/{company_id}", response_model=Company)
def get_company(company_id: int):
    row = store.companies.get(company_id)
    if row is None:
        raise _not_found("Company", company_id)
    return row


@companies.post("", response_model=Company, status_code=201)
def create_company(body: CompanyCreate):
    return store.companies.create(body.model_dump())


@companies.patch("/{company_id}", response_model=Company)
def update_company(company_id: int, body: CompanyUpdate):
    row = store.companies.update(company_id, body.model_dump(exclude_unset=True))
    if row is None:
        raise _not_found("Company", company_id)
    return row


@companies.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, cascade: bool = False):
    if store.companies.get(company_id) is None:
        raise _not_found("Company", company_id)
    linked_contacts = [c for c in store.contacts.all() if c["company_id"] == company_id]
    linked_deals = [d for d in store.deals.all() if d["company_id"] == company_id]
    if (linked_contacts or linked_deals) and not cascade:
        raise HTTPException(
            status_code=409,
            detail=(f"Company has {len(linked_contacts)} contacts and {len(linked_deals)} deals; "
                    "pass cascade=true to delete them too"),
        )
    for c in linked_contacts:
        store.contacts.delete(c["id"])
    for d in linked_deals:
        store.deals.delete(d["id"])
    store.companies.delete(company_id)
    return Response(status_code=204)


@companies.get("/{company_id}/contacts", response_model=list[Contact])
def list_company_contacts(company_id: int):
    if store.companies.get(company_id) is None:
        raise _not_found("Company", company_id)
    return [c for c in store.contacts.all() if c["company_id"] == company_id]


@companies.get("/{company_id}/deals", response_model=list[Deal])
def list_company_deals(company_id: int):
    if store.companies.get(company_id) is None:
        raise _not_found("Company", company_id)
    return [d for d in store.deals.all() if d["company_id"] == company_id]


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #
contacts = APIRouter(prefix="/contacts", tags=["contacts"])


@contacts.get("", response_model=list[Contact])
def list_contacts(
    q: str | None = Query(None, description="Search name, email or title"),
    company_id: int | None = None,
    title: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = [
        c for c in store.contacts.all()
        if (q is None or any(_contains(c[f], q) for f in ("first_name", "last_name", "email", "title"))
            or _contains(f"{c['first_name']} {c['last_name']}", q))
        and (company_id is None or c["company_id"] == company_id)
        and _contains(c["title"], title)
    ]
    return rows[offset: offset + limit]


@contacts.get("/{contact_id}", response_model=Contact)
def get_contact(contact_id: int):
    row = store.contacts.get(contact_id)
    if row is None:
        raise _not_found("Contact", contact_id)
    return row


@contacts.post("", response_model=Contact, status_code=201)
def create_contact(body: ContactCreate):
    _require_company(body.company_id)
    return store.contacts.create(body.model_dump())


@contacts.patch("/{contact_id}", response_model=Contact)
def update_contact(contact_id: int, body: ContactUpdate):
    changes = body.model_dump(exclude_unset=True)
    if "company_id" in changes:
        _require_company(changes["company_id"])
    row = store.contacts.update(contact_id, changes)
    if row is None:
        raise _not_found("Contact", contact_id)
    return row


@contacts.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int):
    if not store.contacts.delete(contact_id):
        raise _not_found("Contact", contact_id)
    # Detach the contact from any deals that referenced it.
    for d in store.deals.all():
        if d["contact_id"] == contact_id:
            store.deals.update(d["id"], {"contact_id": None})
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
deals = APIRouter(prefix="/deals", tags=["deals"])

OPEN_STAGES = {DealStage.prospecting, DealStage.qualification, DealStage.proposal, DealStage.negotiation}


@deals.get("", response_model=list[Deal])
def list_deals(
    q: str | None = Query(None, description="Search deal name or product"),
    company_id: int | None = None,
    contact_id: int | None = None,
    stage: DealStage | None = None,
    owner: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    closing_before: date | None = None,
    closing_after: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = []
    for d in store.deals.all():
        close = date.fromisoformat(str(d["close_date"]))
        if not (q is None or _contains(d["name"], q) or _contains(d["product"], q)):
            continue
        if company_id is not None and d["company_id"] != company_id:
            continue
        if contact_id is not None and d["contact_id"] != contact_id:
            continue
        if stage is not None and d["stage"] != stage.value:
            continue
        if owner is not None and d["owner"].lower() != owner.lower():
            continue
        if min_amount is not None and d["amount_usd"] < min_amount:
            continue
        if max_amount is not None and d["amount_usd"] > max_amount:
            continue
        if closing_before is not None and close > closing_before:
            continue
        if closing_after is not None and close < closing_after:
            continue
        rows.append(d)
    return rows[offset: offset + limit]


@deals.get("/pipeline", response_model=PipelineSummary)
def pipeline_summary(owner: str | None = None):
    rows = [d for d in store.deals.all() if owner is None or d["owner"].lower() == owner.lower()]
    stages = []
    for stage in DealStage:
        in_stage = [d for d in rows if d["stage"] == stage.value]
        total = sum(d["amount_usd"] for d in in_stage)
        weighted = sum(d["amount_usd"] * d["probability"] // 100 for d in in_stage)
        stages.append(PipelineStage(stage=stage, count=len(in_stage),
                                    total_amount_usd=total, weighted_amount_usd=weighted))
    open_stages = [s for s in stages if s.stage in OPEN_STAGES]
    return PipelineSummary(
        total_deals=len(rows),
        open_pipeline_usd=sum(s.total_amount_usd for s in open_stages),
        weighted_pipeline_usd=sum(s.weighted_amount_usd for s in open_stages),
        won_usd=next(s.total_amount_usd for s in stages if s.stage == DealStage.closed_won),
        stages=stages,
    )


@deals.get("/{deal_id}", response_model=Deal)
def get_deal(deal_id: int):
    row = store.deals.get(deal_id)
    if row is None:
        raise _not_found("Deal", deal_id)
    return row


@deals.post("", response_model=Deal, status_code=201)
def create_deal(body: DealCreate):
    _require_company(body.company_id)
    _require_contact(body.contact_id, body.company_id)
    return store.deals.create(body.model_dump(mode="json"))


@deals.patch("/{deal_id}", response_model=Deal)
def update_deal(deal_id: int, body: DealUpdate):
    existing = store.deals.get(deal_id)
    if existing is None:
        raise _not_found("Deal", deal_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    company_id = changes.get("company_id", existing["company_id"])
    if "company_id" in changes:
        _require_company(company_id)
    _require_contact(changes.get("contact_id", existing["contact_id"]), company_id)
    # Keep probability consistent with terminal stages unless explicitly set.
    if "probability" not in changes and changes.get("stage") in ("closed_won", "closed_lost"):
        changes["probability"] = 100 if changes["stage"] == "closed_won" else 0
    return store.deals.update(deal_id, changes)


@deals.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: int):
    if not store.deals.delete(deal_id):
        raise _not_found("Deal", deal_id)
    return Response(status_code=204)


app.include_router(companies)
app.include_router(contacts)
app.include_router(deals)
