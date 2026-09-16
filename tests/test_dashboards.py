from urllib.parse import urlsplit

import pytest
from flask import template_rendered

from test_v2 import application, create_analysis, create_user


ROLES = ("candidate", "recruiter", "admin")


def make_account(role, email="dashboard@example.com"):
    user = create_user(
        name="Dashboard User",
        email=email,
    )
    user.role = role
    application.db.session.commit()
    return user


def sign_in(client, email="dashboard@example.com"):
    return client.post(
        "/login",
        data={
            "email": email,
            "password": "Password123",
        },
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard",
        "/candidate/dashboard",
        "/recruiter/dashboard",
        "/admin/dashboard",
    ],
)
def test_dashboard_requires_login(client, path):
    response = client.get(path)

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/login"


@pytest.mark.parametrize("role", ROLES)
def test_login_redirects_to_correct_dashboard(client, role):
    with application.app.app_context():
        make_account(role)

    response = sign_in(client)

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/dashboard"

    response = client.get("/dashboard")

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == (
        f"/{role}/dashboard"
    )

    response = client.get(response.headers["Location"])

    assert response.status_code == 200
    assert f"{role.capitalize()} Dashboard" in response.get_data(
        as_text=True
    )


@pytest.mark.parametrize("signed_in_role", ROLES)
@pytest.mark.parametrize("page_role", ROLES)
def test_dashboard_role_access(client, signed_in_role, page_role):
    with application.app.app_context():
        make_account(signed_in_role)

    sign_in(client)
    response = client.get(f"/{page_role}/dashboard")

    expected_status = 200 if signed_in_role == page_role else 403
    assert response.status_code == expected_status


@pytest.mark.parametrize("role", ("candidate", "recruiter"))
def test_dashboard_counts_only_own_analyses(client, role):
    with application.app.app_context():
        owner = make_account(role)
        other = make_account(
            "candidate",
            "other-dashboard@example.com",
        )

        create_analysis(owner, "owner.pdf")
        create_analysis(other, "other-one.pdf")
        create_analysis(other, "other-two.pdf")

    sign_in(client)
    rendered = []

    def capture_template(sender, template, context, **extra):
        rendered.append(context)

    with template_rendered.connected_to(
        capture_template,
        application.app,
    ):
        response = client.get(f"/{role}/dashboard")

    assert response.status_code == 200
    assert rendered

    metrics = dict(rendered[-1]["metrics"])

    if role == "candidate":
        assert metrics == {
            "Your saved analyses": 1,
            "Your applications": 0,
            "Under review": 0,
            "Shortlisted": 0,
            "Unread notifications": 0,
        }
    else:
        assert metrics == {
            "Your saved analyses": 1,
            "Your jobs": 0,
            "Open jobs": 0,
            "Applications received": 0,
            "Shortlisted applicants": 0,
            "Unread notifications": 0,
        }


def test_admin_dashboard_shows_platform_totals(client):
    with application.app.app_context():
        make_account("admin")
        candidate = make_account(
            "candidate",
            "candidate@example.com",
        )
        recruiter = make_account(
            "recruiter",
            "recruiter@example.com",
        )

        create_analysis(candidate, "candidate.pdf")
        create_analysis(recruiter, "recruiter.pdf")

    sign_in(client)
    rendered = []

    def capture_template(sender, template, context, **extra):
        rendered.append(context)

    with template_rendered.connected_to(
        capture_template,
        application.app,
    ):
        response = client.get("/admin/dashboard")

    assert response.status_code == 200
    assert rendered

    assert dict(rendered[-1]["metrics"]) == {
        "Total users": 3,
        "Candidates": 1,
        "Recruiters": 1,
        "Administrators": 1,
        "Total analyses": 2,
        "Pending recruiter requests": 0,
        "Unread notifications": 0,
    }