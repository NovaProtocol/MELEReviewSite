from __future__ import annotations

import json


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
        "tags": [],
    }
    q.update(over)
    return q


def test_blocks_rejects_invalid(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    assert r.status_code == 201
    qid = r.json()["id"]
    res = client.put(
        f"/api/questions/{qid}/solution",
        json={"convention": "metric", "blocks": "not json"},
        cookies=cookies,
    )
    assert res.status_code == 422


def test_blocks_rejects_invalid_structure(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    assert r.status_code == 201
    qid = r.json()["id"]
    res = client.put(
        f"/api/questions/{qid}/solution",
        json={"convention": "metric", "blocks": json.dumps([{"type": "unknown"}])},
        cookies=cookies,
    )
    assert res.status_code == 422


def test_blocks_accepts_typed_blocks(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    assert r.status_code == 201
    qid = r.json()["id"]
    blocks = json.dumps(
        [
            {"type": "constants", "constants": [{"name": "P", "value": "100", "unit": "kPa"}]},
            {"type": "formula", "latex": "P*V"},
        ]
    )
    res = client.put(
        f"/api/questions/{qid}/solution",
        json={"convention": "metric", "blocks": blocks},
        cookies=cookies,
    )
    assert res.status_code == 200
    data = res.json()
    parsed = json.loads(data["blocks"])
    assert parsed[0]["type"] == "constants"
    assert parsed[0]["constants"][0]["name"] == "P"


def test_blocks_accepts_legacy_answer(client, account):
    cookies = account["cookies"]
    r = client.post("/api/questions", json=_make_question(), cookies=cookies)
    assert r.status_code == 201
    qid = r.json()["id"]
    res = client.put(
        f"/api/questions/{qid}/solution",
        json={"convention": "metric", "blocks": json.dumps([{"answer": 2}])},
        cookies=cookies,
    )
    assert res.status_code == 200
