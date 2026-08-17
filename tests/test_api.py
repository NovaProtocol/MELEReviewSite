from __future__ import annotations


def _make_question(**over):
    q = {
        "question_text": "What is 2 + 2?",
        "choice_a": "3",
        "choice_b": "4",
        "choice_c": "5",
        "choice_d": "6",
        "choice_e": None,
        "answer": 1,
        "solution": "Basic arithmetic.",
        "active": True,
        "tags": ["Math"],
    }
    q.update(over)
    return q


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_thermo_endpoint(client):
    r = client.post("/api/cycle", json={
        "cycle": "rankine", "input_mode": "fluid", "fluid": "water",
        "parameters": {"P_boiler": 3000000, "P_cond": 10000, "T_turbine": 600},
        "diagram": {"x": "s", "y": "T"},
    })
    assert r.status_code == 200
    data = r.json()
    assert data["solved"] is True
    assert len(data["states"]) == 4
    assert len(data["segments"]) == 4
    assert data["dome"] is not None


def test_thermo_plot_format(client):
    r = client.post("/api/cycle", json={
        "cycle": "carnot", "input_mode": "fluid", "fluid": "water",
        "parameters": {"T_high": 600, "T_low": 300},
        "diagram": {"x": "s", "y": "T"}, "format": "plot",
    })
    data = r.json()
    assert data["solved"] is True
    assert len(data["segments"]) == 4
    assert data["x"] == "s"


def test_accounts_create_list(client):
    r = client.post("/api/auth/accounts", json={"name": "Ana", "pin": "0000"})
    assert r.status_code == 201
    assert r.json()["name"] == "Ana"

    r = client.get("/api/auth/accounts")
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    assert "Ana" in names


def test_login_wrong_pin(client):
    res = client.post("/api/auth/accounts", json={"name": "Bob", "pin": "1111"})
    aid = res.json()["id"]
    r = client.post("/api/auth/login", json={"account_id": aid, "pin": "wrong"})
    assert r.status_code == 401


def test_questions_public_read(client):
    """Questions and answers are readable without login."""
    r = client.get("/api/questions")
    assert r.status_code == 200
    r = client.get("/api/tags")
    assert r.status_code == 200


def test_question_write_requires_login(client):
    r = client.post("/api/questions", json=_make_question())
    assert r.status_code == 401


def test_account_self_delete(client):
    """Soft-delete: disabled accounts are excluded from listing and cannot login."""
    res = client.post("/api/auth/accounts", json={"name": "Temp", "pin": "9999"})
    aid = res.json()["id"]
    login = client.post("/api/auth/login", json={"account_id": aid, "pin": "9999"})
    cookies = login.cookies

    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    qid = r.json()["id"]
    client.put(f"/api/questions/{qid}/solution", json={"blocks": '[{"answer":1}]', "convention": "metric"}, cookies=cookies)

    r = client.delete("/api/auth/me", cookies=cookies)
    assert r.status_code == 204

    accounts = client.get("/api/auth/accounts").json()
    assert all(a["id"] != aid for a in accounts)
    assert client.get("/api/auth/me", cookies=cookies).status_code == 401
    assert client.post("/api/auth/login", json={"account_id": aid, "pin": "9999"}).status_code == 401


def test_question_crud(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    assert r.status_code == 201
    qid = r.json()["id"]
    assert r.json()["tags"] == ["Math"]

    r = client.get("/api/questions", cookies=cookies)
    assert r.status_code == 200
    assert any(q["id"] == qid for q in r.json())

    r = client.put(f"/api/questions/{qid}", json=_make_question(question_text="Edited?", tags=["Math", "Algebra"]), cookies=cookies)
    assert r.status_code == 200
    assert r.json()["question_text"] == "Edited?"
    assert set(r.json()["tags"]) == {"Math", "Algebra"}

    r = client.get("/api/tags", cookies=cookies)
    assert r.status_code == 200
    assert {"Math", "Algebra"} <= {t["name"] for t in r.json()}


def test_question_inactive_hidden(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(question_text="Hidden Q", active=False), cookies=cookies)
    qid = r.json()["id"]

    r = client.get("/api/questions", cookies=cookies)
    assert all(q["id"] != qid for q in r.json())

    r = client.get("/api/questions?include_inactive=true", cookies=cookies)
    assert any(q["id"] == qid for q in r.json())


def test_question_delete_cascades_solutions(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    qid = r.json()["id"]

    r = client.put(f"/api/questions/{qid}/solution", json={"blocks": '[{"answer":1}]', "convention": "metric"}, cookies=cookies)
    assert r.status_code == 200
    assert client.get(f"/api/questions/{qid}/solution", cookies=cookies).status_code == 200

    r = client.delete(f"/api/questions/{qid}", cookies=cookies)
    assert r.status_code == 204

    # solution gone with the question
    assert client.get(f"/api/questions/{qid}/solution", cookies=cookies).status_code == 404
    assert client.get(f"/api/questions/{qid}", cookies=cookies).status_code == 404


def test_solution_per_account(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    qid = r.json()["id"]

    r = client.put(f"/api/questions/{qid}/solution", json={"blocks": '[{"answer":1}]', "convention": "metric"}, cookies=cookies)
    assert r.status_code == 200
    assert r.json()["blocks"] == '[{"answer":1}]'

    r = client.get(f"/api/questions/{qid}/solution", cookies=cookies)
    assert r.status_code == 200
    assert r.json()["blocks"] == '[{"answer":1}]'

    r = client.get("/api/my/solutions", cookies=cookies)
    assert r.status_code == 200
    assert any(s["question_id"] == qid for s in r.json())


def test_flag_question(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    qid = r.json()["id"]
    r = client.post(f"/api/questions/{qid}/flag", cookies=cookies)
    assert r.json()["flagged"] is True


def test_disabled_account_rejected(client):
    """Disabled account cannot login or access /me."""
    res = client.post("/api/auth/accounts", json={"name": "Disabled", "pin": "2222"})
    aid = res.json()["id"]

    # Login first, then soft-delete
    login = client.post("/api/auth/login", json={"account_id": aid, "pin": "2222"})
    cookies = login.cookies
    client.delete("/api/auth/me", cookies=cookies)

    # Login is rejected
    r = client.post("/api/auth/login", json={"account_id": aid, "pin": "2222"})
    assert r.status_code == 401

    # /me returns 401 even with old session cookie
    r = client.get("/api/auth/me", cookies=cookies)
    assert r.status_code == 401


def test_non_owner_cannot_edit_or_delete(client, account):
    owner_cookies = account["cookies"]

    # Create a second account (non-owner)
    r = client.post("/api/auth/accounts", json={"name": "Other", "pin": "5678"})
    other_id = r.json()["id"]
    r = client.post("/api/auth/login", json={"account_id": other_id, "pin": "5678"})
    other_cookies = r.cookies

    # Owner creates a question
    r = client.post("/api/questions", json=_make_question(), cookies=owner_cookies)
    qid = r.json()["id"]
    assert r.json()["author_name"] == "Nova"

    # Non-owner cannot edit
    r = client.put(f"/api/questions/{qid}", json=_make_question(question_text="Hacked"), cookies=other_cookies)
    assert r.status_code == 403

    # Non-owner cannot delete
    r = client.delete(f"/api/questions/{qid}", cookies=other_cookies)
    assert r.status_code == 403

    # Owner can still edit
    r = client.put(f"/api/questions/{qid}", json=_make_question(question_text="Owner edit"), cookies=owner_cookies)
    assert r.status_code == 200
    assert r.json()["question_text"] == "Owner edit"


def test_others_solutions_endpoint(client, account):
    """GET /api/questions/{id}/solutions returns solutions with account names."""
    cookies = account["cookies"]

    # Create a second account
    r = client.post("/api/auth/accounts", json={"name": "Alice", "pin": "3333"})
    alice_id = r.json()["id"]
    r = client.post("/api/auth/login", json={"account_id": alice_id, "pin": "3333"})
    alice_cookies = r.cookies

    # Owner creates a question
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    qid = r.json()["id"]

    # Both accounts submit solutions
    client.put(f"/api/questions/{qid}/solution", json={"blocks": '[{"answer":1}]', "convention": "metric"}, cookies=cookies)
    client.put(f"/api/questions/{qid}/solution", json={"blocks": '[{"answer":2}]', "convention": "imperial"}, cookies=alice_cookies)

    # List solutions for question (no auth required)
    r = client.get(f"/api/questions/{qid}/solutions")
    assert r.status_code == 200
    sols = r.json()
    assert len(sols) == 2
    names = {s["account_name"] for s in sols}
    assert names == {"Nova", "Alice"}
    for s in sols:
        assert "account_name" in s
        assert "blocks" in s
        assert "date_created" in s
