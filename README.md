# B2B CRM: REST API + MCP server

A small CRM for a B2B software sales team with three constructs:

| Construct | Sample data | What it holds |
|-----------|-------------|---------------|
| **Companies** | 10 fictional B2B software companies (analytics, fintech, security, DevOps, HR tech…) | name, domain, industry, employees, revenue, HQ |
| **Contacts** | 20 people (2 per company) | name, email, phone, title, `company_id` |
| **Deals** | 18 deals across every pipeline stage | amount, stage, probability, close date, owner, product, `company_id`, `contact_id` |

All companies and people are invented. The sample data is loaded automatically the first time the app starts with an empty database.

One app serves all of:
- the **web UI** at `/`: dashboard, a drag-and-drop deals board, and companies and contacts with create, edit and delete
- the **REST API** (interactive docs at `/docs`)
- the **MCP server** at `/mcp` (Streamable HTTP)

```
api/static/   Web UI (single page, no build step)
api/          FastAPI app, database models, service layer, API-key auth
mcp_server/   MCP tools (served at /mcp, or over stdio for local use)
tests/        API, auth and MCP tests
Dockerfile    Container image (used by Render, Railway, Fly, ...)
render.yaml   Render Blueprint: web service + Postgres
```

## Deploy to Render

1. In the Render dashboard, click **New → Blueprint** and pick this repository.
2. Click **Apply**. Render creates the web service and a Postgres database, generates an `API_KEY`, builds the Dockerfile, and deploys.
3. Open the service's **Environment** tab and copy the value of `API_KEY`.

Your app is then live at `https://<service-name>.onrender.com`:
- `https://<service-name>.onrender.com/`: the web UI. Sign in with the API key; it's remembered in that browser until you sign out.
- `https://<service-name>.onrender.com/docs`: click **Authorize** and paste the key to try the API in your browser
- `https://<service-name>.onrender.com/mcp`: the MCP endpoint

Every push to `main` redeploys automatically.

Free-plan notes: the web service sleeps after 15 minutes of inactivity, so the first request afterwards takes about 30 seconds. Render's free Postgres is deleted 30 days after creation unless you upgrade it. For always-on hosting with a database that's kept, change `plan: free` to `starter` (web) and `basic-256mb` (database) in `render.yaml`.

### Configuration

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres connection string (set by the Blueprint). Defaults to a local SQLite file `crm.db`. |
| `API_KEY` | Required on every request except the UI page (`/`), `/health` and `/docs`. If unset, the app is open (local dev only). |
| `ALLOWED_HOSTS` | Extra comma-separated hostnames the MCP endpoint accepts, e.g. a custom domain. Render's own hostname is added automatically. |

## Authentication

Send the key in one of these ways:

```bash
curl -H "X-API-Key: $API_KEY" https://<service>.onrender.com/companies
```

```bash
curl -H "Authorization: Bearer $API_KEY" https://<service>.onrender.com/companies
```

You can also append `?api_key=$API_KEY` to the URL, for clients that can't set headers. Prefer the headers when you can, because URLs often end up in logs.

## Connect the hosted MCP server

**Claude Code:**

```bash
claude mcp add --transport http b2b-crm https://<service>.onrender.com/mcp --header "X-API-Key: <your key>"
```

**Claude.ai / Claude Desktop (custom connector):** add a custom connector with the URL `https://<service>.onrender.com/mcp?api_key=<your key>`.

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

Errors such as "Company 999 not found" or invalid input come back to the model as tool errors.

## REST endpoints

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

## Run locally

Requires Python 3.10+. On macOS or Linux:

```bash
./setup.sh
```

This finds Python 3.10+ (installing 3.12 with Homebrew if needed), creates `.venv`, installs dependencies and starts the app at http://localhost:8000/docs. Data is stored in `crm.db`. Delete that file to reset to the sample data.

Manual setup:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

To use the MCP server locally over stdio (no web server needed), run this from the repo root:

```bash
claude mcp add b2b-crm -- "$(pwd)/.venv/bin/python" -m mcp_server
```

Or run it with Docker:

```bash
docker build -t b2b-crm . && docker run -p 8000:8000 -e API_KEY=changeme b2b-crm
```

## Tests

```bash
pytest -q
```

To run the tests against Postgres instead of in-memory SQLite:

```bash
TEST_DATABASE_URL=postgresql://user@localhost/crm_test pytest -q
```
