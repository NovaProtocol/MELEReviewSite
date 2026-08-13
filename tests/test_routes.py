from __future__ import annotations


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_landing_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "MELE" in r.text
    assert "Start Learning" in r.text


def test_sources_page_empty(client):
    r = client.get("/sources")
    assert r.status_code == 200
    assert "Sources" in r.text


def test_openapi_exposes_routes(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/sources" in paths
    assert "/api/sources/{source_id}/questions" in paths
    assert "/api/questions/{question_id}/solution" in paths
    assert "/api/questions/{question_id}/answer" in paths


def test_api_requires_access_password(client):
    r = client.post("/api/sources", files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code in (401, 422)


def test_api_upload_source_with_password(client):
    pdf = b"%PDF-1.4\nSOURCE_UNIQUE_12345\n%%EOF"
    r = client.post(
        "/api/sources",
        files={"file": ("test.pdf", pdf, "application/pdf")},
        data={"title": "Test Source"},
        headers={"x-access-password": "test-password"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Test Source"
    assert body["question_count"] == 0
    assert len(body["pdf_hash"]) == 64


def test_api_upload_questions(client):
    pdf = b"%PDF-1.4\nQ_SOURCE_PDF_UNIQUE\n%%EOF"
    r = client.post(
        "/api/sources",
        files={"file": ("test.pdf", pdf, "application/pdf")},
        data={"title": "Q Source"},
        headers={"x-access-password": "test-password"},
    )
    assert r.status_code == 201, r.text
    source_id = r.json()["id"]

    r = client.post(
        f"/api/sources/{source_id}/questions",
        json=[
            {
                "question_text": "What is 2 + 2?",
                "choice_a": "3",
                "choice_b": "4",
                "choice_c": "5",
                "choice_d": "6",
                "answer": 1,
            },
            {
                "question_text": "What is the capital of France?",
                "choice_a": "London",
                "choice_b": "Paris",
                "choice_c": "Berlin",
                "choice_d": "Madrid",
                "answer": 1,
            },
        ],
        headers={"x-access-password": "test-password"},
    )
    assert r.status_code == 201
    assert r.json()["count"] == 2

    r = client.get(f"/api/sources/{source_id}/questions")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 2


def test_api_update_solution(client):
    pdf = b"%PDF-1.4 SOL_UNIQUE"
    r = client.post(
        "/api/sources",
        files={"file": ("t.pdf", pdf, "application/pdf")},
        data={"title": "Sol Source"},
        headers={"x-access-password": "test-password"},
    )
    source_id = r.json()["id"]
    r = client.post(
        f"/api/sources/{source_id}/questions",
        json=[
            {
                "question_text": "Q1",
                "choice_a": "a",
                "choice_b": "b",
                "choice_c": "c",
                "choice_d": "d",
                "answer": 0,
            }
        ],
        headers={"x-access-password": "test-password"},
    )
    question_id = r.json()["count"]
    r = client.get(f"/api/sources/{source_id}/questions")
    question_id = r.json()["data"][0]["id"]

    r = client.put(
        f"/api/questions/{question_id}/solution",
        json={"blocks": '[{"type":"formula","latex":"x = -b/(2a)","result":""}]', "convention": "metric"},
        headers={"x-access-password": "test-password"},
    )
    assert r.status_code == 200
    assert "formula" in r.json()["blocks"]


def test_api_update_answer(client):
    pdf = b"%PDF-1.4 ANS_UNIQUE"
    r = client.post(
        "/api/sources",
        files={"file": ("t.pdf", pdf, "application/pdf")},
        data={"title": "Ans Source"},
        headers={"x-access-password": "test-password"},
    )
    source_id = r.json()["id"]
    r = client.post(
        f"/api/sources/{source_id}/questions",
        json=[
            {
                "question_text": "Q1",
                "choice_a": "a",
                "choice_b": "b",
                "choice_c": "c",
                "choice_d": "d",
                "answer": None,
            }
        ],
        headers={"x-access-password": "test-password"},
    )
    r = client.get(f"/api/sources/{source_id}/questions")
    question_id = r.json()["data"][0]["id"]

    r = client.put(
        f"/api/questions/{question_id}/answer",
        json={"answer": 2},
        headers={"x-access-password": "test-password"},
    )
    assert r.status_code == 200
    assert r.json()["answer"] == 2

    r = client.get("/api/sources")
    src = [s for s in r.json()["data"] if s["id"] == source_id][0]
    assert src["answered_count"] == 1


def test_login_logout(client):
    r = client.post("/auth/login", data={"access_password": "wrong-password"}, follow_redirects=False)
    assert r.status_code == 303

    r = client.post("/auth/login", data={"access_password": "test-password"}, follow_redirects=False)
    assert r.status_code == 303
    assert "access_token" in r.headers.get("set-cookie", "")

    cookies = r.cookies
    r = client.get("/sources", cookies=cookies)
    assert r.status_code == 200


def test_source_pdf_download(client):
    pdf = b"%PDF-1.4\nPDF_SRC_UNIQUE\n%%EOF"
    r = client.post(
        "/api/sources",
        files={"file": ("test.pdf", pdf, "application/pdf")},
        data={"title": "PDF Source"},
        headers={"x-access-password": "test-password"},
    )
    source_id = r.json()["id"]
    r = client.get(f"/api/sources/{source_id}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == pdf


def test_source_questions_page(client):
    pdf = b"%PDF-1.4\nPAGE_SRC_UNIQUE\n%%EOF"
    r = client.post(
        "/api/sources",
        files={"file": ("t.pdf", pdf, "application/pdf")},
        data={"title": "Page Source"},
        headers={"x-access-password": "test-password"},
    )
    source_id = r.json()["id"]
    client.post(
        f"/api/sources/{source_id}/questions",
        json=[
            {
                "question_text": "Test question text",
                "choice_a": "A",
                "choice_b": "B",
                "choice_c": "C",
                "choice_d": "D",
                "answer": 0,
            }
        ],
        headers={"x-access-password": "test-password"},
    )
    r = client.get(f"/sources/{source_id}")
    assert r.status_code == 200
    assert "Test question text" in r.text


def _login(client):
    r = client.post("/auth/login", data={"access_password": "test-password"}, follow_redirects=False)
    assert r.status_code == 303
    return r.cookies


def test_web_source_upload_requires_write(client):
    client.cookies.clear()
    r = client.get("/sources/new", follow_redirects=False)
    assert r.status_code == 401

    r = client.post(
        "/sources/new",
        files={"file": ("t.pdf", b"%PDF-1.4 WEB_UNIQUE_1\n%%EOF", "application/pdf")},
        data={"title": "Web Source"},
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_web_source_upload(client):
    cookies = _login(client)
    r = client.get("/sources/new", cookies=cookies)
    assert r.status_code == 200
    assert "Upload Source" in r.text

    r = client.post(
        "/sources/new",
        files={"file": ("t.pdf", b"%PDF-1.4 WEB_UNIQUE_2\n%%EOF", "application/pdf")},
        data={"title": "Web Source"},
        cookies=cookies,
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/sources/")

    r = client.get("/sources", cookies=cookies)
    assert "Web Source" in r.text


def test_web_question_upload(client):
    cookies = _login(client)
    pdf = b"%PDF-1.4 WEB_UNIQUE_3\n%%EOF"
    r = client.post(
        "/api/sources",
        files={"file": ("t.pdf", pdf, "application/pdf")},
        data={"title": "Web Q Source"},
        headers={"x-access-password": "test-password"},
    )
    source_id = r.json()["id"]

    r = client.get(f"/sources/{source_id}/questions/new", cookies=cookies)
    assert r.status_code == 200

    r = client.post(
        f"/sources/{source_id}/questions/new",
        data={
            "question_text": "Web question?",
            "choice_a": "A",
            "choice_b": "B",
            "choice_c": "C",
            "choice_d": "D",
            "choice_e": "",
            "answer": "2",
        },
        cookies=cookies,
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.get(f"/sources/{source_id}")
    assert "Web question?" in r.text


def test_web_question_upload_requires_write(client):
    client.cookies.clear()
    pdf = b"%PDF-1.4 WEB_UNIQUE_4\n%%EOF"
    r = client.post(
        "/api/sources",
        files={"file": ("t.pdf", pdf, "application/pdf")},
        data={"title": "Web Q NoAuth"},
        headers={"x-access-password": "test-password"},
    )
    source_id = r.json()["id"]

    r = client.get(f"/sources/{source_id}/questions/new", follow_redirects=False)
    assert r.status_code == 401

    r = client.post(
        f"/sources/{source_id}/questions/new",
        data={
            "question_text": "Nope?",
            "choice_a": "A",
            "choice_b": "B",
            "choice_c": "C",
            "choice_d": "D",
            "answer": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_solution_editor(client):
    _login(client)
    pdf = b"%PDF-1.4 SOL_TEST"
    r = client.post("/api/sources", files={"file": ("t.pdf", pdf, "application/pdf")}, data={"title": "Sol Test"}, headers={"x-access-password": "test-password"})
    sid = r.json()["id"]
    r = client.post(f"/api/sources/{sid}/questions", json=[{"question_text": "Find m if f=ma", "choice_a": "5", "choice_b": "10", "choice_c": "15", "choice_d": "20", "answer": 1}], headers={"x-access-password": "test-password"})
    q = client.get(f"/api/sources/{sid}/questions").json()["data"][0]
    qid = q["id"]

    r = client.get(f"/api/questions/{qid}/solution")
    assert r.status_code == 200
    assert r.json()["blocks"] == "[]"

    blocks = '[{"type":"constants","constants":[{"name":"f","value":"10","unit":"N"}]},{"type":"formula","latex":"f=m*9.81","result":""}]'
    r = client.put(f"/api/questions/{qid}/solution", json={"blocks": blocks, "convention": "metric"}, headers={"x-access-password": "test-password"})
    assert r.status_code == 200

    r = client.get(f"/api/questions/{qid}/solution")
    assert r.status_code == 200
    assert "f" in r.json()["blocks"]

    # Solution write must require auth (no header/cookie -> 401)
    client.cookies.clear()
    r = client.put(f"/api/questions/{qid}/solution", json={"blocks": "[]", "convention": "metric"})
    assert r.status_code == 401

    # Inline editor renders MathQuill on the questions page (write mode)
    _login(client)
    r = client.get(f"/sources/{sid}")
    assert r.status_code == 200
    assert "MathQuill" in r.text and "MathQuill.getInterface" in r.text


def test_flag_and_filters(client):
    _login(client)
    pdf = b"%PDF-1.4 FLAG_TEST"
    r = client.post("/api/sources", files={"file": ("t.pdf", pdf, "application/pdf")}, data={"title": "Flag Test"}, headers={"x-access-password": "test-password"})
    sid = r.json()["id"]
    qs = [
        {"question_text": "Answered Q", "choice_a": "a", "choice_b": "b", "choice_c": "c", "choice_d": "d", "answer": 0},
        {"question_text": "Unanswered Q", "choice_a": "a", "choice_b": "b", "choice_c": "c", "choice_d": "d", "answer": None},
    ]
    client.post(f"/api/sources/{sid}/questions", json=qs, headers={"x-access-password": "test-password"})
    data = client.get(f"/api/sources/{sid}/questions").json()["data"]
    qid = data[0]["id"]

    # flag requires auth
    client.cookies.clear()
    r = client.post(f"/api/questions/{qid}/flag")
    assert r.status_code == 401

    # flag on/off
    _login(client)
    r = client.post(f"/api/questions/{qid}/flag")
    assert r.status_code == 200 and r.json()["flagged"] is True
    r = client.post(f"/api/questions/{qid}/flag")
    assert r.json()["flagged"] is False

    # flagged filter
    client.post(f"/api/questions/{qid}/flag")
    r = client.get(f"/sources/{sid}?status=flagged")
    assert "Showing 1 of 1" in r.text
    assert "Flag" in r.text

    # answered/unanswered filters
    r = client.get(f"/sources/{sid}?status=answered")
    assert "Showing 1 of 1" in r.text
    r = client.get(f"/sources/{sid}?status=unanswered")
    assert "Showing 1 of 1" in r.text

    # search
    r = client.get(f"/sources/{sid}?q=Answered")
    assert "Showing 1 of 1" in r.text
    assert "Answered Q" in r.text
