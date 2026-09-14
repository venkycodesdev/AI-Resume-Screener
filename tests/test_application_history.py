from urllib.parse import urlsplit

import pytest
from flask import template_rendered

from test_v2 import application, create_user


HISTORY_URL = "/candidate/applications"

STATUSES = (
    "submitted",
    "under_review",
    "shortlisted",
    "rejected",
    "hired",
    "withdrawn",
)


@pytest.fixture
def history_accounts(client):
    with application.app.app_context():
        candidate = create_user(
            name="History Candidate",
            email="history-candidate@example.com",
        )
        candidate.role = "candidate"

        other = create_user(
            name="Other Candidate",
            email="history-other@example.com",
        )
        other.role = "candidate"

        recruiter = create_user(
            name="History Recruiter",
            email="history-recruiter@example.com",
        )
        recruiter.role = "recruiter"

        application.db.session.commit()

        return {
            "candidate_id": candidate.id,
            "other_id": other.id,
            "recruiter_id": recruiter.id,
        }


def add_submission(accounts, title, status="submitted", candidate_id=None):
    job = application.JobPosting(
        recruiter_id=accounts["recruiter_id"],
        title=title,
        company="Demo Company",
        location="Hyderabad",
        description="Python development position.",
        employment_type="full_time",
        status="open",
    )
    application.db.session.add(job)
    application.db.session.flush()

    submission = application.JobApplication(
        candidate_id=(
            accounts["candidate_id"]
            if candidate_id is None
            else candidate_id
        ),
        job_id=job.id,
        resume_filename="history-resume.pdf",
        resume_content=b"History test fixture",
        resume_text="Python developer.",
        job_title_snapshot=title,
        job_description_snapshot=job.description,
        status=status,
    )
    application.db.session.add(submission)
    application.db.session.commit()

    return submission.id, job.id


def sign_in(client, email="history-candidate@example.com"):
    response = client.post(
        "/login",
        data={"email": email, "password": "Password123"},
    )
    assert response.status_code == 302


def fetch_history(client, query=None):
    captured = []

    def capture(sender, template, context, **extra):
        captured.append(context)

    with template_rendered.connected_to(capture, application.app):
        response = client.get(
            HISTORY_URL,
            query_string=query or {},
        )

    assert response.status_code == 200
    return response, captured[-1]["pagination"]


def test_history_requires_login(client):
    response = client.get(HISTORY_URL)

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/login"


@pytest.mark.parametrize("role", ["recruiter", "admin"])
def test_history_blocks_other_roles(client, role):
    with application.app.app_context():
        user = create_user(email="history-blocked@example.com")
        user.role = role
        application.db.session.commit()

    sign_in(client, "history-blocked@example.com")

    assert client.get(HISTORY_URL).status_code == 403


def test_history_shows_only_own_applications(client, history_accounts):
    with application.app.app_context():
        own_id, _ = add_submission(
            history_accounts,
            "My Private Application",
        )
        add_submission(
            history_accounts,
            "Other Private Application",
            candidate_id=history_accounts["other_id"],
        )

    sign_in(client)
    response, pagination = fetch_history(client)

    assert pagination.total == 1
    assert [item.id for item in pagination.items] == [own_id]

    html = response.get_data(as_text=True)
    assert "My Private Application" in html
    assert "Other Private Application" not in html

    confirmation = client.get(f"{HISTORY_URL}/{own_id}")
    assert confirmation.status_code == 200


@pytest.mark.parametrize("status", STATUSES)
def test_history_filters_by_status(client, history_accounts, status):
    with application.app.app_context():
        expected_id = None

        for value in STATUSES:
            submission_id, _ = add_submission(
                history_accounts,
                f"Application {value}",
                status=value,
            )
            if value == status:
                expected_id = submission_id

        # Another candidate's matching status must remain hidden.
        add_submission(
            history_accounts,
            "Other Candidate Match",
            status=status,
            candidate_id=history_accounts["other_id"],
        )

    sign_in(client)
    _, pagination = fetch_history(client, {"status": status})

    assert pagination.total == 1
    assert [item.id for item in pagination.items] == [expected_id]


def test_history_pagination_preserves_filter(client, history_accounts):
    with application.app.app_context():
        expected_ids = []

        for index in range(11):
            submission_id, _ = add_submission(
                history_accounts,
                f"Submitted Position {index}",
            )
            expected_ids.append(submission_id)

        add_submission(
            history_accounts,
            "Rejected Position",
            status="rejected",
        )

    sign_in(client)
    response, first = fetch_history(
        client,
        {"status": "submitted"},
    )
    _, second = fetch_history(
        client,
        {"status": "submitted", "page": 2},
    )

    first_ids = [item.id for item in first.items]
    second_ids = [item.id for item in second.items]

    assert first.total == 11
    assert len(first_ids) == 10
    assert len(second_ids) == 1
    assert set(first_ids).isdisjoint(second_ids)
    assert set(first_ids + second_ids) == set(expected_ids)

    html = response.get_data(as_text=True)
    assert "page=2" in html
    assert "status=submitted" in html


@pytest.mark.parametrize(
    "query",
    [
        {"page": "abc"},
        {"page": "0"},
        {"page": "-1"},
        {"status": "invalid"},
    ],
)
def test_history_rejects_invalid_filters(client, history_accounts, query):
    sign_in(client)

    response = client.get(HISTORY_URL, query_string=query)

    assert response.status_code == 400


def test_empty_history_shows_browse_link(client, history_accounts):
    sign_in(client)
    response, pagination = fetch_history(client)

    assert pagination.total == 0

    html = response.get_data(as_text=True)
    assert "No matching applications" in html
    assert 'href="/candidate/jobs"' in html


def test_application_remains_visible_after_job_closes(
    client, history_accounts
):
    with application.app.app_context():
        submission_id, job_id = add_submission(
            history_accounts,
            "Original Job Title",
        )

        job = application.db.session.get(
            application.JobPosting,
            job_id,
        )
        job.status = "closed"
        job.title = "Changed Job Title"
        application.db.session.commit()

    sign_in(client)
    response, pagination = fetch_history(client)

    assert [item.id for item in pagination.items] == [submission_id]

    html = response.get_data(as_text=True)
    assert "Original Job Title" in html
    assert "Changed Job Title" not in html

    confirmation = client.get(f"{HISTORY_URL}/{submission_id}")
    assert confirmation.status_code == 200