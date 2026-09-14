from urllib.parse import urlsplit

import pytest
from flask import template_rendered

from test_v2 import application, create_user


JOBS_URL = "/candidate/jobs"


def add_job(owner_id, title="Python Developer", **overrides):
    values = {
        "recruiter_id": owner_id,
        "title": title,
        "company": "Demo Company",
        "location": "Hyderabad",
        "description": "Build Python applications.",
        "employment_type": "full_time",
        "status": "open",
    }
    values.update(overrides)

    job = application.JobPosting(**values)
    application.db.session.add(job)
    application.db.session.commit()
    return job.id


@pytest.fixture
def browsing_accounts(client):
    with application.app.app_context():
        candidate = create_user(
            name="Candidate",
            email="candidate-browse@example.com",
        )
        candidate.role = "candidate"

        recruiter = create_user(
            name="Recruiter",
            email="recruiter-browse@example.com",
        )
        recruiter.role = "recruiter"

        application.db.session.commit()
        return recruiter.id


def login_candidate(client):
    response = client.post(
        "/login",
        data={
            "email": "candidate-browse@example.com",
            "password": "Password123",
        },
    )
    assert response.status_code == 302


def fetch_listing(client, query=None):
    captured = []

    def capture(sender, template, context, **extra):
        captured.append(context)

    with template_rendered.connected_to(capture, application.app):
        response = client.get(JOBS_URL, query_string=query or {})

    assert response.status_code == 200
    return response, captured[-1]["pagination"]


@pytest.mark.parametrize(
    "path",
    [JOBS_URL, f"{JOBS_URL}/1"],
)
def test_candidate_jobs_require_login(client, path):
    response = client.get(path)

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/login"


@pytest.mark.parametrize("role", ["recruiter", "admin"])
@pytest.mark.parametrize(
    "path",
    [JOBS_URL, f"{JOBS_URL}/1"],
)
def test_candidate_jobs_block_other_roles(client, role, path):
    with application.app.app_context():
        user = create_user()
        user.role = role
        application.db.session.commit()

    client.post(
        "/login",
        data={
            "email": "test@example.com",
            "password": "Password123",
        },
    )

    assert client.get(path).status_code == 403


def test_listing_shows_only_open_jobs(client, browsing_accounts):
    with application.app.app_context():
        open_id = add_job(browsing_accounts, title="Visible Opening")
        add_job(
            browsing_accounts,
            title="Private Draft",
            status="draft",
        )
        add_job(
            browsing_accounts,
            title="Closed Position",
            status="closed",
        )

    login_candidate(client)
    response, pagination = fetch_listing(client)

    assert [job.id for job in pagination.items] == [open_id]
    html = response.get_data(as_text=True)
    assert "Private Draft" not in html
    assert "Closed Position" not in html


@pytest.mark.parametrize("status", ["draft", "closed"])
def test_hidden_job_details_are_unavailable(
    client, browsing_accounts, status
):
    with application.app.app_context():
        job_id = add_job(
            browsing_accounts,
            title="Hidden Position",
            status=status,
        )

    login_candidate(client)
    response = client.get(f"{JOBS_URL}/{job_id}")

    assert response.status_code == 404
    assert "Hidden Position" not in response.get_data(as_text=True)


def test_open_details_show_description(client, browsing_accounts):
    with application.app.app_context():
        job_id = add_job(
            browsing_accounts,
            description="Unique description for this position.",
        )

    login_candidate(client)
    response = client.get(f"{JOBS_URL}/{job_id}")

    assert response.status_code == 200
    assert "Unique description for this position." in response.get_data(
        as_text=True
    )


def test_missing_job_returns_404(client, browsing_accounts):
    login_candidate(client)

    assert client.get(f"{JOBS_URL}/999999").status_code == 404


@pytest.mark.parametrize(
    "field,value,search",
    [
        ("title", "Python Developer", "pYtHoN"),
        ("company", "Example Labs", "example"),
        ("location", "Bengaluru", "bengaluru"),
    ],
)
def test_search_matches_job_fields(
    client, browsing_accounts, field, value, search
):
    with application.app.app_context():
        match_id = add_job(browsing_accounts, **{field: value})
        add_job(
            browsing_accounts,
            title="Unrelated Position",
            company="Other Company",
            location="Chennai",
        )

    login_candidate(client)
    _, pagination = fetch_listing(client, {"q": search})

    assert [job.id for job in pagination.items] == [match_id]


def test_search_and_type_filter_work_together(client, browsing_accounts):
    with application.app.app_context():
        match_id = add_job(
            browsing_accounts,
            title="Python Intern",
            employment_type="internship",
        )
        add_job(
            browsing_accounts,
            title="Python Engineer",
            employment_type="full_time",
        )
        add_job(
            browsing_accounts,
            title="Design Intern",
            employment_type="internship",
        )

    login_candidate(client)
    _, pagination = fetch_listing(
        client,
        {"q": "Python", "employment_type": "internship"},
    )

    assert [job.id for job in pagination.items] == [match_id]


@pytest.mark.parametrize("symbol", ["%", "_", "\\"])
def test_search_treats_wildcards_literally(
    client, browsing_accounts, symbol
):
    with application.app.app_context():
        match_id = add_job(
            browsing_accounts,
            title=f"Special {symbol} Position",
        )
        add_job(browsing_accounts, title="Ordinary Position")

    login_candidate(client)
    _, pagination = fetch_listing(client, {"q": symbol})

    assert [job.id for job in pagination.items] == [match_id]


def test_pagination_preserves_filters(client, browsing_accounts):
    with application.app.app_context():
        for index in range(13):
            add_job(
                browsing_accounts,
                title=f"Python Internship {index}",
                employment_type="internship",
            )
        add_job(browsing_accounts, title="Unrelated Position")

    login_candidate(client)
    filters = {"q": "Python", "employment_type": "internship"}

    response, first = fetch_listing(client, filters)
    _, second = fetch_listing(client, {**filters, "page": 2})

    assert first.total == 13
    assert len(first.items) == 12
    assert len(second.items) == 1
    assert {job.id for job in first.items}.isdisjoint(
        {job.id for job in second.items}
    )

    html = response.get_data(as_text=True)
    assert "page=2" in html
    assert "q=Python" in html
    assert "employment_type=internship" in html


@pytest.mark.parametrize(
    "query",
    [
        {"page": "abc"},
        {"page": "0"},
        {"page": "-1"},
        {"q": "x" * 151},
        {"employment_type": "invalid"},
    ],
)
def test_invalid_search_parameters_return_400(
    client, browsing_accounts, query
):
    login_candidate(client)

    response = client.get(JOBS_URL, query_string=query)

    assert response.status_code == 400


def test_empty_results_show_helpful_message(client, browsing_accounts):
    login_candidate(client)
    response, pagination = fetch_listing(client)

    assert pagination.total == 0
    assert "No matching jobs" in response.get_data(as_text=True)


def test_closing_job_removes_candidate_access(client, browsing_accounts):
    with application.app.app_context():
        job_id = add_job(browsing_accounts)

    login_candidate(client)
    assert client.get(f"{JOBS_URL}/{job_id}").status_code == 200

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        job.status = "closed"
        application.db.session.commit()

    assert client.get(f"{JOBS_URL}/{job_id}").status_code == 404
    _, pagination = fetch_listing(client)
    assert pagination.total == 0