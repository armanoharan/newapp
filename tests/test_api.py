def test_seed_data_loaded(client):
    assert len(client.get("/companies").json()) == 10
    assert len(client.get("/contacts").json()) == 20
    assert len(client.get("/deals").json()) == 18


def test_company_crud(client):
    body = {"name": "Testco", "domain": "testco.io", "industry": "SaaS", "employees": 5,
            "annual_revenue_usd": 1000, "hq_city": "Paris", "country": "France"}
    created = client.post("/companies", json=body).json()
    assert created["id"] == 11
    assert client.patch(f"/companies/{created['id']}", json={"employees": 9}).json()["employees"] == 9
    assert client.delete(f"/companies/{created['id']}").status_code == 204
    assert client.get(f"/companies/{created['id']}").status_code == 404


def test_company_delete_requires_cascade(client):
    assert client.delete("/companies/1").status_code == 409
    assert client.delete("/companies/1?cascade=true").status_code == 204
    assert client.get("/contacts?company_id=1").json() == []
    assert client.get("/deals?company_id=1").json() == []


def test_contact_filters_and_validation(client):
    assert {c["company_id"] for c in client.get("/contacts?company_id=3").json()} == {3}
    assert client.get("/contacts?q=priya").json()[0]["last_name"] == "Raman"
    bad = {"first_name": "A", "last_name": "B", "email": "a@b.co", "title": "X", "company_id": 999}
    assert client.post("/contacts", json=bad).status_code == 422


def test_deal_create_and_close(client):
    body = {"name": "New deal", "company_id": 2, "contact_id": 3, "amount_usd": 10_000,
            "close_date": "2027-05-01", "owner": "Sam Rivera", "product": "Platform"}
    deal = client.post("/deals", json=body).json()
    assert deal["stage"] == "prospecting"
    won = client.patch(f"/deals/{deal['id']}", json={"stage": "closed_won"}).json()
    assert won["probability"] == 100


def test_deal_contact_must_match_company(client):
    body = {"name": "Bad", "company_id": 2, "contact_id": 1, "amount_usd": 1,
            "close_date": "2027-05-01", "owner": "x", "product": "y"}
    assert client.post("/deals", json=body).status_code == 422


def test_deal_filters(client):
    rows = client.get("/deals?stage=negotiation&min_amount=200000").json()
    assert rows and all(d["stage"] == "negotiation" and d["amount_usd"] >= 200_000 for d in rows)
    rows = client.get("/deals?closing_before=2026-12-31&closing_after=2026-12-01").json()
    assert {d["id"] for d in rows} == {1, 6, 16}


def test_pipeline_summary(client):
    s = client.get("/deals/pipeline").json()
    assert s["total_deals"] == 18
    assert s["won_usd"] == 42_000 + 25_000 + 150_000
    assert sum(st["count"] for st in s["stages"]) == 18
