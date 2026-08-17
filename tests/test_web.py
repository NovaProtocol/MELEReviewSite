from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from web.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def page():
    with TestClient(create_app()) as c:
        yield c


def test_home_serves_questions(page):
    r = page.get("/")
    assert r.status_code == 200
    assert "q-list" in r.text


def test_login_page(page):
    r = page.get("/login")
    assert r.status_code == 200
    assert "Create New Account" in r.text
    assert "account-grid" in r.text


def test_profile_page(page):
    r = page.get("/profile")
    assert r.status_code == 200
    assert "profile-page" in r.text


def test_questions_page(page):
    r = page.get("/questions")
    assert r.status_code == 200
    assert "q-list" in r.text


def test_question_form(page):
    r = page.get("/questions/new")
    assert r.status_code == 200
    assert "question-form" in r.text


def test_calculators_index(page):
    r = page.get("/calculators")
    assert r.status_code == 200
    for name in ("Thermo Cycles", "Unit Converter", "Fluid Mechanics", "Machine Design"):
        assert name in r.text


def test_thermo_calculator(page):
    r = page.get("/calculators/thermo?cycle=rankine")
    assert r.status_code == 200
    assert "cycle-select" in r.text


def test_calculator_pages(page):
    for path in ("/calculators/unit", "/calculators/fluids", "/calculators/strength", "/calculators/heat", "/calculators/psychro", "/calculators/machine"):
        r = page.get(path)
        assert r.status_code == 200, path
