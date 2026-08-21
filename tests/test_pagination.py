from __future__ import annotations


def _make_question(text="Sample question?", **over):
    q = {
        "question_text": text,
        "choice_a": "A",
        "choice_b": "B",
        "choice_c": "C",
        "choice_d": "D",
        "choice_e": None,
        "answer": 1,
        "solution": None,
        "active": True,
        "tags": [],
    }
    q.update(over)
    return q


def test_list_questions_pagination_header(client, account):
    cookies = account["cookies"]

    # Count existing to isolate this test's expectations
    before = client.get("/api/questions?per_page=100", cookies=cookies)
    assert before.status_code == 200
    n_before = int(before.headers.get("X-Total-Count", len(before.json())))

    # Create 25 new questions
    for i in range(25):
        r = client.post(
            "/api/questions",
            json=_make_question(text=f"Paginated Q {i}"),
            cookies=cookies,
        )
        assert r.status_code == 201, r.text

    # Page 1, per_page 10 -> 10 items, total header = n_before + 25
    r = client.get("/api/questions?page=1&per_page=10", cookies=cookies)
    assert r.status_code == 200
    assert len(r.json()) == 10
    assert "X-Total-Count" in r.headers, "missing X-Total-Count header"
    assert int(r.headers["X-Total-Count"]) == n_before + 25

    # Envelope mode returns object
    r = client.get("/api/questions?page=1&per_page=10&envelope=true", cookies=cookies)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict), "envelope=true should return dict"
    assert "items" in body and "total" in body
    assert body["total"] == n_before + 25
    assert len(body["items"]) == 10
    assert body["page"] == 1
    assert body["per_page"] == 10


def test_search_case_insensitive(client, account):
    cookies = account["cookies"]
    unique = "ThermoDynamicsUnIqUe"
    r = client.post(
        "/api/questions",
        json=_make_question(text=f"{unique} case test question"),
        cookies=cookies,
    )
    assert r.status_code == 201, r.text
    qid = r.json()["id"]

    # Lowercase search should still find it
    r = client.get(f"/api/questions?search={unique.lower()}", cookies=cookies)
    assert r.status_code == 200
    ids = [q["id"] for q in r.json()]
    assert qid in ids, "case-insensitive search failed (lowercase)"

    # Uppercase search should also find it
    r = client.get(f"/api/questions?search={unique.upper()}", cookies=cookies)
    assert r.status_code == 200
    ids = [q["id"] for q in r.json()]
    assert qid in ids, "case-insensitive search failed (uppercase)"


def test_request_id_header(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers, "missing X-Request-ID response header"


def test_cors_headers(client):
    # CORS preflight: Origin header should yield Access-Control-Allow-Origin
    r = client.get("/health", headers={"Origin": "http://example.com"})
    # If CORS is enabled, header will be present
    assert r.status_code == 200
    # We expect the header to be echoed or *
    assert "access-control-allow-origin" in {k.lower() for k in r.headers.keys()}
