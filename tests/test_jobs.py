from urllib.parse import urlsplit

import pytest

from test_v2 import application, create_user


JOBS_URL = "/recruiter/jobs"


def make_user(role, email="recruiter@example.com"):
    user = create_user(name="Job Test User", email=email)
    user.role = role
    application.db.session.commit()
    return user.id


def sign_in(client, email="recruiter@example.com"):
    return client.post(
        "/login",
        data={"email": email, "password": "Password123"},
    )


def valid_form(client):
    response = client.get(JOBS_URL)
    assert response.status_code == 200

    with client.session_transaction() as session:
        token = session["job_csrf_token"]

    return {
        "csrf_token": token,
        "title": "Python Developer",
        "company": "Example Company",
        "location": "Hyderabad",
        "description": "Build and maintain Python and Flask applications.",
        "employment_type": "full_time",
    }


@pytest.mark.parametrize("method", ["get", "post"])
def test_jobs_require_login(client, method):
    response = getattr(client, method)(JOBS_URL)

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/login"


@pytest.mark.parametrize("role", ["candidate", "admin"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_jobs_require_recruiter_role(client, role, method):
    with application.app.app_context():
        make_user(role)

    sign_in(client)
    response = getattr(client, method)(JOBS_URL)

    assert response.status_code == 403


def test_create_job_uses_logged_in_owner_and_draft_status(client):
    with application.app.app_context():
        owner_id = make_user("recruiter")
        other_id = make_user("recruiter", "other@example.com")

    sign_in(client)
    data = valid_form(client)

    # Submitted ownership and status must not override server values.
    data["recruiter_id"] = str(other_id)
    data["status"] = "open"

    response = client.post(JOBS_URL, data=data)

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == JOBS_URL

    with application.app.app_context():
        job = application.JobPosting.query.one()

        assert job.recruiter_id == owner_id
        assert job.status == "draft"
        assert job.title == "Python Developer"
        assert job.employment_type == "full_time"


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "   "),
        ("company", ""),
        ("location", ""),
        ("description", ""),
        ("title", "x" * 151),
        ("company", "x" * 151),
        ("location", "x" * 151),
        ("description", "x" * 20001),
        ("employment_type", "invalid"),
    ],
)
def test_invalid_job_is_not_saved(client, field, value):
    with application.app.app_context():
        make_user("recruiter")

    sign_in(client)
    data = valid_form(client)
    data[field] = value

    response = client.post(JOBS_URL, data=data)

    assert response.status_code == 400
    assert "Please correct the following" in response.get_data(
        as_text=True
    )

    with application.app.app_context():
        assert application.JobPosting.query.count() == 0


@pytest.mark.parametrize("token", [None, "incorrect-token"])
def test_invalid_csrf_token_is_rejected(client, token):
    with application.app.app_context():
        make_user("recruiter")

    sign_in(client)
    data = valid_form(client)

    if token is None:
        data.pop("csrf_token")
    else:
        data["csrf_token"] = token

    response = client.post(JOBS_URL, data=data)

    assert response.status_code == 400

    with application.app.app_context():
        assert application.JobPosting.query.count() == 0


def test_recruiter_sees_only_own_jobs(client):
    with application.app.app_context():
        owner_id = make_user("recruiter")
        other_id = make_user("recruiter", "other@example.com")

        for recruiter_id, title in [
            (owner_id, "Owner Private Posting"),
            (other_id, "Other Private Posting"),
        ]:
            application.db.session.add(
                application.JobPosting(
                    recruiter_id=recruiter_id,
                    title=title,
                    company="Example Company",
                    location="Hyderabad",
                    description="Python development position.",
                    employment_type="full_time",
                    status="draft",
                )
            )

        application.db.session.commit()

    sign_in(client)
    response = client.get(JOBS_URL)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Owner Private Posting" in html
    assert "Other Private Posting" not in html


def make_job(recruiter_id, status="draft"):
    job = application.JobPosting(
        recruiter_id=recruiter_id,
        title="Original Job",
        company="Example Company",
        location="Hyderabad",
        description="Original job description.",
        employment_type="full_time",
        status=status,
    )
    application.db.session.add(job)
    application.db.session.commit()
    return job.id


def test_owner_can_edit_job_without_changing_owner_or_status(client):
    with application.app.app_context():
        owner_id = make_user("recruiter")
        other_id = make_user("recruiter", "other@example.com")
        job_id = make_job(owner_id)

    sign_in(client)
    response = client.get(f"{JOBS_URL}/{job_id}/edit")

    assert response.status_code == 200
    assert "Original Job" in response.get_data(as_text=True)

    data = valid_form(client)
    data["title"] = "Updated Python Job"
    data["recruiter_id"] = str(other_id)
    data["status"] = "open"

    response = client.post(f"{JOBS_URL}/{job_id}/edit", data=data)

    assert response.status_code == 302

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        assert job.title == "Updated Python Job"
        assert job.recruiter_id == owner_id
        assert job.status == "draft"


def test_invalid_edit_preserves_original_job(client):
    with application.app.app_context():
        owner_id = make_user("recruiter")
        job_id = make_job(owner_id)

    sign_in(client)
    data = valid_form(client)
    data["title"] = "   "

    response = client.post(f"{JOBS_URL}/{job_id}/edit", data=data)

    assert response.status_code == 400

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        assert job.title == "Original Job"


@pytest.mark.parametrize(
    "old_status,new_status",
    [
        ("draft", "open"),
        ("open", "closed"),
        ("closed", "open"),
        ("draft", "closed"),
    ],
)
def test_owner_can_change_job_status(client, old_status, new_status):
    with application.app.app_context():
        owner_id = make_user("recruiter")
        job_id = make_job(owner_id, status=old_status)

    sign_in(client)
    data = valid_form(client)

    response = client.post(
        f"{JOBS_URL}/{job_id}/status",
        data={
            "csrf_token": data["csrf_token"],
            "status": new_status,
        },
    )

    assert response.status_code == 302

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        assert job.status == new_status


@pytest.mark.parametrize("operation", ["edit", "status"])
@pytest.mark.parametrize("token", [None, "incorrect-token"])
def test_job_changes_require_valid_csrf(client, operation, token):
    with application.app.app_context():
        owner_id = make_user("recruiter")
        job_id = make_job(owner_id)

    sign_in(client)
    data = valid_form(client)
    data["title"] = "Unauthorized Change"
    data["status"] = "open"

    if token is None:
        data.pop("csrf_token")
    else:
        data["csrf_token"] = token

    response = client.post(
        f"{JOBS_URL}/{job_id}/{operation}",
        data=data,
    )

    assert response.status_code == 400

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        assert job.title == "Original Job"
        assert job.status == "draft"


@pytest.mark.parametrize("operation", ["edit", "status"])
def test_other_recruiter_cannot_change_job(client, operation):
    with application.app.app_context():
        make_user("recruiter")
        other_id = make_user("recruiter", "other@example.com")
        job_id = make_job(other_id)

    sign_in(client)
    data = valid_form(client)
    data["title"] = "Unauthorized Change"
    data["status"] = "open"

    if operation == "edit":
        response = client.get(f"{JOBS_URL}/{job_id}/edit")
        assert response.status_code == 404

    response = client.post(
        f"{JOBS_URL}/{job_id}/{operation}",
        data=data,
    )

    assert response.status_code == 404

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        assert job.title == "Original Job"
        assert job.status == "draft"


def test_invalid_status_preserves_job(client):
    with application.app.app_context():
        owner_id = make_user("recruiter")
        job_id = make_job(owner_id)

    sign_in(client)
    data = valid_form(client)

    response = client.post(
        f"{JOBS_URL}/{job_id}/status",
        data={
            "csrf_token": data["csrf_token"],
            "status": "invalid",
        },
    )

    assert response.status_code == 400

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        assert job.status == "draft"


@pytest.mark.parametrize("role", ["candidate", "admin"])
@pytest.mark.parametrize("operation", ["edit", "status"])
def test_non_recruiter_cannot_change_jobs(client, role, operation):
    with application.app.app_context():
        make_user(role)
        owner_id = make_user("recruiter", "owner@example.com")
        job_id = make_job(owner_id)

    sign_in(client)

    if operation == "edit":
        response = client.get(f"{JOBS_URL}/{job_id}/edit")
        assert response.status_code == 403

    response = client.post(
        f"{JOBS_URL}/{job_id}/{operation}",
        data={"title": "Unauthorized Change", "status": "open"},
    )

    assert response.status_code == 403

    with application.app.app_context():
        job = application.db.session.get(application.JobPosting, job_id)
        assert job.title == "Original Job"
        assert job.status == "draft"