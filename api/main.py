"""FastAPI application: REST APIs for Companies, Contacts and Deals, plus the MCP server at /mcp."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response, Security
from pathlib import Path

from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader

from mcp_server.server import mcp, mcp_http_app

from . import service
from .auth import APIKeyMiddleware
from .db import init_db
from .models import (
    Company, CompanyCreate, CompanyUpdate,
    Contact, ContactCreate, ContactUpdate,
    Deal, DealCreate, DealStage, DealUpdate,
    PipelineSummary,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with mcp.session_manager.run():
        yield


# Declared so Swagger UI shows an "Authorize" button; enforcement is in APIKeyMiddleware.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(
    title="B2B CRM API",
    version="2.0.0",
    description=("Companies, Contacts and Deals for a B2B software sales team. "
                 "Send your key in the `X-API-Key` header. The MCP server is served at `/mcp`."),
    lifespan=lifespan,
    dependencies=[Security(api_key_header)],
)
app.add_middleware(APIKeyMiddleware)


@app.exception_handler(service.NotFound)
async def _not_found(_: Request, exc: service.NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(service.Conflict)
async def _conflict(_: Request, exc: service.Conflict):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(service.Invalid)
async def _invalid(_: Request, exc: service.Invalid):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


UI_FILE = Path(__file__).parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    """The web UI. It's public; every API call it makes sends the API key."""
    return FileResponse(UI_FILE, headers={"Cache-Control": "no-cache"})


@app.get("/api", tags=["meta"])
def api_info() -> dict:
    return {"service": "b2b-crm", "ui": "/", "docs": "/docs", "mcp": "/mcp",
            "resources": ["/companies", "/contacts", "/deals"]}


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
    return service.list_companies(q, industry, country, min_employees, limit, offset)


@companies.get("/{company_id}", response_model=Company)
def get_company(company_id: int):
    return service.get_company(company_id)


@companies.post("", response_model=Company, status_code=201)
def create_company(body: CompanyCreate):
    return service.create_company(body.model_dump())


@companies.patch("/{company_id}", response_model=Company)
def update_company(company_id: int, body: CompanyUpdate):
    return service.update_company(company_id, body.model_dump(exclude_unset=True))


@companies.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, cascade: bool = False):
    service.delete_company(company_id, cascade)
    return Response(status_code=204)


@companies.get("/{company_id}/contacts", response_model=list[Contact])
def list_company_contacts(company_id: int):
    return service.company_contacts(company_id)


@companies.get("/{company_id}/deals", response_model=list[Deal])
def list_company_deals(company_id: int):
    return service.company_deals(company_id)


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
    return service.list_contacts(q, company_id, title, limit, offset)


@contacts.get("/{contact_id}", response_model=Contact)
def get_contact(contact_id: int):
    return service.get_contact(contact_id)


@contacts.post("", response_model=Contact, status_code=201)
def create_contact(body: ContactCreate):
    return service.create_contact(body.model_dump())


@contacts.patch("/{contact_id}", response_model=Contact)
def update_contact(contact_id: int, body: ContactUpdate):
    return service.update_contact(contact_id, body.model_dump(exclude_unset=True))


@contacts.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int):
    service.delete_contact(contact_id)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
deals = APIRouter(prefix="/deals", tags=["deals"])


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
    return service.list_deals(q, company_id, contact_id, stage.value if stage else None, owner,
                              min_amount, max_amount, closing_before, closing_after, limit, offset)


@deals.get("/pipeline", response_model=PipelineSummary)
def pipeline_summary(owner: str | None = None):
    return service.pipeline_summary(owner)


@deals.get("/{deal_id}", response_model=Deal)
def get_deal(deal_id: int):
    return service.get_deal(deal_id)


@deals.post("", response_model=Deal, status_code=201)
def create_deal(body: DealCreate):
    data = body.model_dump()
    data["stage"] = body.stage.value
    return service.create_deal(data)


@deals.patch("/{deal_id}", response_model=Deal)
def update_deal(deal_id: int, body: DealUpdate):
    changes = body.model_dump(exclude_unset=True)
    if body.stage is not None:
        changes["stage"] = body.stage.value
    return service.update_deal(deal_id, changes)


@deals.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: int):
    service.delete_deal(deal_id)
    return Response(status_code=204)


app.include_router(companies)
app.include_router(contacts)
app.include_router(deals)

# MCP (Streamable HTTP) at /mcp. Mounted last so the REST routes above take precedence.
app.mount("/", mcp_http_app)
