"""MCP server exposing the B2B CRM (Companies, Contacts, Deals) as tools.

Tools call the same service layer as the REST API, so there is no separate API process.

- Hosted: served by the main app at /mcp (Streamable HTTP), behind the same API key.
- Local stdio (Claude Desktop / Claude Code):  python -m mcp_server
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Any, Callable, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError

from api import service
from api.models import (
    Company, CompanyCreate, CompanyUpdate,
    Contact, ContactCreate, ContactUpdate,
    Deal, DealCreate, DealUpdate,
)

Stage = Literal["prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"]

mcp = MCPServer(
    name="b2b-crm",
    instructions=(
        "Tools for a B2B software CRM with three resources: companies, contacts and deals. "
        "Contacts and deals belong to a company via company_id; deals may reference a contact_id. "
        "Use the list_* tools with filters to find ids before calling get/update/delete."
    ),
)


def _tool(fn: Callable) -> Callable:
    """Register a tool and turn service/validation errors into MCP tool errors."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except service.ServiceError as exc:
            raise ToolError(str(exc)) from exc
        except ValidationError as exc:
            msgs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            raise ToolError(f"Invalid input: {msgs}") from exc
    return mcp.tool()(wrapper)


def _changes(local_vars: dict[str, Any], id_field: str) -> dict[str, Any]:
    return {k: v for k, v in local_vars.items() if k != id_field and v is not None}


def _company(row: dict) -> dict:
    return Company.model_validate(row).model_dump(mode="json")


def _contact(row: dict) -> dict:
    return Contact.model_validate(row).model_dump(mode="json")


def _deal(row: dict) -> dict:
    return Deal.model_validate(row).model_dump(mode="json")


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
@_tool
def list_companies(q: str | None = None, industry: str | None = None, country: str | None = None,
                   min_employees: int | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """List companies. `q` searches name/domain/description; `industry` is a substring match."""
    return [_company(r) for r in service.list_companies(q, industry, country, min_employees, limit, offset)]


@_tool
def get_company(company_id: int) -> dict:
    """Get one company by id."""
    return _company(service.get_company(company_id))


@_tool
def get_company_contacts(company_id: int) -> list[dict]:
    """List all contacts that work at a company."""
    return [_contact(r) for r in service.company_contacts(company_id)]


@_tool
def get_company_deals(company_id: int) -> list[dict]:
    """List all deals for a company."""
    return [_deal(r) for r in service.company_deals(company_id)]


@_tool
def create_company(name: str, domain: str, industry: str, employees: int, annual_revenue_usd: int,
                   hq_city: str, country: str, description: str = "") -> dict:
    """Create a company."""
    return _company(service.create_company(CompanyCreate(**locals()).model_dump()))


@_tool
def update_company(company_id: int, name: str | None = None, domain: str | None = None,
                   industry: str | None = None, employees: int | None = None,
                   annual_revenue_usd: int | None = None, hq_city: str | None = None,
                   country: str | None = None, description: str | None = None) -> dict:
    """Update fields on a company. Only the fields you pass are changed."""
    changes = CompanyUpdate(**_changes(locals(), "company_id")).model_dump(exclude_unset=True)
    return _company(service.update_company(company_id, changes))


@_tool
def delete_company(company_id: int, cascade: bool = False) -> dict:
    """Delete a company. Fails if it has contacts/deals unless cascade=True (which deletes them too)."""
    service.delete_company(company_id, cascade)
    return {"deleted": True, "company_id": company_id}


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #
@_tool
def list_contacts(q: str | None = None, company_id: int | None = None, title: str | None = None,
                  limit: int = 100, offset: int = 0) -> list[dict]:
    """List contacts. `q` searches name/email/title; `title` is a substring match (e.g. 'VP')."""
    return [_contact(r) for r in service.list_contacts(q, company_id, title, limit, offset)]


@_tool
def get_contact(contact_id: int) -> dict:
    """Get one contact by id."""
    return _contact(service.get_contact(contact_id))


@_tool
def create_contact(first_name: str, last_name: str, email: str, title: str, company_id: int,
                   phone: str = "") -> dict:
    """Create a contact at an existing company."""
    return _contact(service.create_contact(ContactCreate(**locals()).model_dump()))


@_tool
def update_contact(contact_id: int, first_name: str | None = None, last_name: str | None = None,
                   email: str | None = None, phone: str | None = None, title: str | None = None,
                   company_id: int | None = None) -> dict:
    """Update fields on a contact. Only the fields you pass are changed."""
    changes = ContactUpdate(**_changes(locals(), "contact_id")).model_dump(exclude_unset=True)
    return _contact(service.update_contact(contact_id, changes))


@_tool
def delete_contact(contact_id: int) -> dict:
    """Delete a contact. Deals that referenced it keep existing with contact_id cleared."""
    service.delete_contact(contact_id)
    return {"deleted": True, "contact_id": contact_id}


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
@_tool
def list_deals(q: str | None = None, company_id: int | None = None, contact_id: int | None = None,
               stage: Stage | None = None, owner: str | None = None, min_amount: int | None = None,
               max_amount: int | None = None, closing_before: str | None = None,
               closing_after: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """List deals with filters. Dates are YYYY-MM-DD. `q` searches deal name/product."""
    from datetime import date

    try:
        before = date.fromisoformat(closing_before) if closing_before else None
        after = date.fromisoformat(closing_after) if closing_after else None
    except ValueError as exc:
        raise ToolError(f"Dates must be YYYY-MM-DD: {exc}") from exc
    rows = service.list_deals(q, company_id, contact_id, stage, owner, min_amount, max_amount,
                              before, after, limit, offset)
    return [_deal(r) for r in rows]


@_tool
def get_deal(deal_id: int) -> dict:
    """Get one deal by id."""
    return _deal(service.get_deal(deal_id))


@_tool
def get_pipeline_summary(owner: str | None = None) -> dict:
    """Pipeline totals per stage (count, total and probability-weighted amount), optionally for one owner."""
    return service.pipeline_summary(owner)


@_tool
def create_deal(name: str, company_id: int, amount_usd: int, close_date: str, owner: str, product: str,
                stage: Stage = "prospecting", probability: int = 10, contact_id: int | None = None) -> dict:
    """Create a deal. close_date is YYYY-MM-DD; contact_id must belong to the same company."""
    body = DealCreate(**locals())
    data = body.model_dump()
    data["stage"] = body.stage.value
    return _deal(service.create_deal(data))


@_tool
def update_deal(deal_id: int, name: str | None = None, company_id: int | None = None,
                contact_id: int | None = None, amount_usd: int | None = None, stage: Stage | None = None,
                probability: int | None = None, close_date: str | None = None, owner: str | None = None,
                product: str | None = None) -> dict:
    """Update fields on a deal (e.g. move stage). Closing a deal auto-sets probability to 100/0."""
    body = DealUpdate(**_changes(locals(), "deal_id"))
    changes = body.model_dump(exclude_unset=True)
    if body.stage is not None:
        changes["stage"] = body.stage.value
    return _deal(service.update_deal(deal_id, changes))


@_tool
def delete_deal(deal_id: int) -> dict:
    """Delete a deal."""
    service.delete_deal(deal_id)
    return {"deleted": True, "deal_id": deal_id}


# --------------------------------------------------------------------------- #
# HTTP app (mounted by api.main) and stdio entry point
# --------------------------------------------------------------------------- #
def _allowed_hosts() -> list[str]:
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):  # set automatically by Render
        hosts.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
    hosts += [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
    return hosts


_hosts = _allowed_hosts()
mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,   # no in-memory sessions: survives restarts and works with several instances
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_hosts,
        allowed_origins=[f"https://{h}" for h in _hosts if "*" not in h]
        + ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", "https://claude.ai"],
    ),
)


def main() -> None:
    from api.db import init_db

    init_db()
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
