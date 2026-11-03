# B2B CRM: REST API + MCP server

A small CRM for a B2B software sales team with three constructs:

| Construct | Sample data | What it holds |
|-----------|-------------|---------------|
| **Companies** | 10 fictional B2B software companies (analytics, fintech, security, DevOps, HR tech…) | name, domain, industry, employees, revenue, HQ |
| **Contacts** | 20 people (2 per company) | name, email, phone, title, `company_id` |
| **Deals** | 18 deals across every pipeline stage | amount, stage, probability, close date, owner, product, `company_id`, `contact_id` |

All companies and people are invented.

```
api/          FastAPI REST API (in-memory store seeded from api/seed_data.py)
mcp_server/   MCP server exposing the API as 18 tools
tests/        API tests
```

## Setup

Requires Python 3.10+. The quickest way (macOS/Linux):

```bash
./setup.sh
```

This finds Python 3.10+ (installing 3.12 with Homebrew if needed), creates `.venv`, installs dependencies and starts the API at http://localhost:8000/docs.

Manual setup:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn api.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

Data lives in memory and resets to the sample data on every restart.

### Endpoints

**Companies**
- `GET /companies`: filters `q`, `industry`, `country`, `min_employees`, `limit`, `offset`
- `GET /companies/{id}`, `POST /companies`, `PATCH /companies/{id}`
- `DELETE /companies/{id}?cascade=true`: returns 409 if the company still has contacts or deals, unless `cascade=true`
- `GET /companies/{id}/contacts`, `GET /companies/{id}/deals`

**Contacts**
- `GET /contacts`: filters `q`, `company_id`, `title`
- `GET /contacts/{id}`, `POST /contacts`, `PATCH /contacts/{id}`, `DELETE /contacts/{id}`

**Deals**
- `GET /deals`: filters `q`, `company_id`, `contact_id`, `stage`, `owner`, `min_amount`, `max_amount`, `closing_before`, `closing_after`
- `GET /deals/pipeline`: count, total and weighted amount per stage (optional `owner`)
- `GET /deals/{id}`, `POST /deals`, `PATCH /deals/{id}`, `DELETE /deals/{id}`

Stages: `prospecting`, `qualification`, `proposal`, `negotiation`, `closed_won`, `closed_lost`.
Moving a deal to `closed_won` or `closed_lost` sets its probability to 100 or 0. The API checks that each `company_id` exists and that a deal's contact works at the deal's company.

```bash
curl "localhost:8000/deals?stage=negotiation&min_amount=200000"
curl -X PATCH localhost:8000/deals/11 -H 'content-type: application/json' -d '{"stage":"closed_won"}'
```

## Run the MCP server

The MCP server calls the REST API, so start the API first. Set `CRM_API_URL` if the API is not at `http://localhost:8000`.

**stdio** (Claude Desktop, Claude Code, etc.):

```bash
python -m mcp_server
```

**Streamable HTTP** (served at `http://127.0.0.1:8001/mcp`):

```bash
python -m mcp_server --http --port 8001
```

### Add it to Claude Code

```bash
claude mcp add b2b-crm -e CRM_API_URL=http://localhost:8000 -- python -m mcp_server
```

Run that from the repo root. For Claude Desktop, add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "b2b-crm": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/b2b-crm",
      "env": { "CRM_API_URL": "http://localhost:8000" }
    }
  }
}
```

### Tools

| Companies | Contacts | Deals |
|-----------|----------|-------|
| `list_companies` | `list_contacts` | `list_deals` |
| `get_company` | `get_contact` | `get_deal` |
| `get_company_contacts` | `create_contact` | `get_pipeline_summary` |
| `get_company_deals` | `update_contact` | `create_deal` |
| `create_company` | `delete_contact` | `update_deal` |
| `update_company` | | `delete_deal` |
| `delete_company` | | |

Errors from the API (such as "Company 999 not found") come back to the model as tool errors.

## Tests

```bash
pytest -q
```
