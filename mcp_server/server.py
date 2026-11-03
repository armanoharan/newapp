"""MCP server that exposes the B2B CRM REST API (Companies, Contacts, Deals) as tools.

The server is a thin client over the HTTP API, so the API must be running.
Configure the API location with CRM_API_URL (default http://localhost:8000).

Run over stdio (for Claude Desktop / Claude Code):
    python -m mcp_server.server
Run over Streamable HTTP:
    python -m mcp_server.server --http --port 8001
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

API_URL = os.environ.get("CRM_API_URL", "http://localhost:8000").rstrip("/")

Stage = Literal["prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"]

mcp = MCPServer(
    name="b2b-crm",
    instructions=(
        "Tools for a B2B software CRM with three resources: companies, contacts and deals. "
        "Contacts and deals belong to a company via company_id; deals may reference a contact_id. "
        "Use the list_* tools with filters to find ids before calling get/update/delete."
    ),
)

_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(base_url=API_URL, timeout=15.0)
    return _client


def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> Any:
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    clean_json = None if json is None else {k: v for k, v in json.items() if v is not None}
    try:
        resp = _http().request(method, path, params=clean_params, json=clean_json)
    except httpx.HTTPError as exc:
        raise ToolError(f"Could not reach CRM API at {API_URL}: {exc}") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ToolError(f"CRM API error {resp.status_code}: {detail}")
    if resp.status_code == 204 or not resp.content:
        return {"ok": True}
    return resp.json()


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_companies(
    q: str | None = None,
    industry: str | None = None,
    country: str | None = None,
    min_employees: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List companies. `q` searches name/domain/description; `industry` is a substring match."""
    return _request("GET", "/companies", params=locals())


@mcp.tool()
def get_company(company_id: int) -> dict:
    """Get one company by id."""
    return _request("GET", f"/companies/{company_id}")


@mcp.tool()
def get_company_contacts(company_id: int) -> list[dict]:
    """List all contacts that work at a company."""
    return _request("GET", f"/companies/{company_id}/contacts")


@mcp.tool()
def get_company_deals(company_id: int) -> list[dict]:
    """List all deals for a company."""
    return _request("GET", f"/companies/{company_id}/deals")


@mcp.tool()
def create_company(
    name: str,
    domain: str,
    industry: str,
    employees: int,
    annual_revenue_usd: int,
    hq_city: str,
    country: str,
    description: str = "",
) -> dict:
    """Create a company."""
    return _request("POST", "/companies", json=locals())


@mcp.tool()
def update_company(
    company_id: int,
    name: str | None = None,
    domain: str | None = None,
    industry: str | None = None,
    employees: int | None = None,
    annual_revenue_usd: int | None = None,
    hq_city: str | None = None,
    country: str | None = None,
    description: str | None = None,
) -> dict:
    """Update fields on a company. Only the fields you pass are changed."""
    body = {k: v for k, v in locals().items() if k != "company_id"}
    return _request("PATCH", f"/companies/{company_id}", json=body)


@mcp.tool()
def delete_company(company_id: int, cascade: bool = False) -> dict:
    """Delete a company. Fails if it has contacts/deals unless cascade=True (which deletes them too)."""
    return _request("DELETE", f"/companies/{company_id}", params={"cascade": str(cascade).lower()})


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_contacts(
    q: str | None = None,
    company_id: int | None = None,
    title: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List contacts. `q` searches name/email/title; `title` is a substring match (e.g. 'VP')."""
    return _request("GET", "/contacts", params=locals())


@mcp.tool()
def get_contact(contact_id: int) -> dict:
    """Get one contact by id."""
    return _request("GET", f"/contacts/{contact_id}")


@mcp.tool()
def create_contact(
    first_name: str,
    last_name: str,
    email: str,
    title: str,
    company_id: int,
    phone: str = "",
) -> dict:
    """Create a contact at an existing company."""
    return _request("POST", "/contacts", json=locals())


@mcp.tool()
def update_contact(
    contact_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    title: str | None = None,
    company_id: int | None = None,
) -> dict:
    """Update fields on a contact. Only the fields you pass are changed."""
    body = {k: v for k, v in locals().items() if k != "contact_id"}
    return _request("PATCH", f"/contacts/{contact_id}", json=body)


@mcp.tool()
def delete_contact(contact_id: int) -> dict:
    """Delete a contact. Deals that referenced it keep existing with contact_id cleared."""
    return _request("DELETE", f"/contacts/{contact_id}")


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_deals(
    q: str | None = None,
    company_id: int | None = None,
    contact_id: int | None = None,
    stage: Stage | None = None,
    owner: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    closing_before: str | None = None,
    closing_after: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List deals with filters. Dates are YYYY-MM-DD. `q` searches deal name/product."""
    return _request("GET", "/deals", params=locals())


@mcp.tool()
def get_deal(deal_id: int) -> dict:
    """Get one deal by id."""
    return _request("GET", f"/deals/{deal_id}")


@mcp.tool()
def get_pipeline_summary(owner: str | None = None) -> dict:
    """Pipeline totals per stage (count, total and probability-weighted amount), optionally for one owner."""
    return _request("GET", "/deals/pipeline", params={"owner": owner})


@mcp.tool()
def create_deal(
    name: str,
    company_id: int,
    amount_usd: int,
    close_date: str,
    owner: str,
    product: str,
    stage: Stage = "prospecting",
    probability: int = 10,
    contact_id: int | None = None,
) -> dict:
    """Create a deal. close_date is YYYY-MM-DD; contact_id must belong to the same company."""
    return _request("POST", "/deals", json=locals())


@mcp.tool()
def update_deal(
    deal_id: int,
    name: str | None = None,
    company_id: int | None = None,
    contact_id: int | None = None,
    amount_usd: int | None = None,
    stage: Stage | None = None,
    probability: int | None = None,
    close_date: str | None = None,
    owner: str | None = None,
    product: str | None = None,
) -> dict:
    """Update fields on a deal (e.g. move stage). Closing a deal auto-sets probability to 100/0."""
    body = {k: v for k, v in locals().items() if k != "deal_id"}
    return _request("PATCH", f"/deals/{deal_id}", json=body)


@mcp.tool()
def delete_deal(deal_id: int) -> dict:
    """Delete a deal."""
    return _request("DELETE", f"/deals/{deal_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="B2B CRM MCP server")
    parser.add_argument("--http", action="store_true", help="Serve over Streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
