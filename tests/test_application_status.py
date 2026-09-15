from datetime import datetime

import pytest

from test_v2 import application, create_user


@pytest.fixture
def status_data(client):
    with application.app.app_context():
        recruiter = create_user(
            name="Status Recruiter",
            email="status-recruiter@example.com",
        )
        recruiter.role = "recruiter"

        candidate = create_user(
            name="Status Candidate",
            email="status-candidate@example.com",
        )
        candidate.role = "candidate"

        job = application.JobPosting(
            recruiter_id=recruiter.id,
            title="Python Developer",
            company="Test Company",
            location="Hyderabad",
            description="Build Python applications using Flask.",
            employment_type="full_time",
            status="open",
        )
        application.db.session.add(job)
        application.db.session.flush()

        submission = application.JobApplication(
            candidate_id=candidate.id,
            job_id=job.id,
            resume_filename="resume.pdf",
            resume_content=b"test-resume-content",
            resume_text="Python developer with Flask experience.",
            job_title_snapshot=job.title,
            job_description_snapshot=job.description,
            status="submitted",
            submitted_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        application.db.session.add(submission)
        application.db.session.commit()

        return {
            "application_id": submission.id,
            "job_id": job.id,
            "list_url": f"/recruiter/jobs/{job.id}/applicants",
            "update_url": (
                f"/recruiter/jobs/{job.id}/applications/"
                f"{submission.id}/status"
            ),
        }


def sign_in(client, email="status-recruiter@example.com"):
    response = client.post(
        "/login",
        data={
            "email": email,
            "password": "Password123",
        },
    )
    assert response.status_code == 302


def get_token(client, data):
    response = client.get(data["list_url"])
    assert response.status_code == 200

    with client.session_transaction() as session:
        return session["application_status_csrf_token"]


def set_status(data, status):
    with application.app.app_context():
        submission = application.db.session.get(
            application.JobApplication,
            data["application_id"],
        )
        submission.status = status
        application.db.session.commit()

        # Set the baseline after the status update has been flushed.
        submission.updated_at = datetime(2026, 1, 1)
        application.db.session.commit()


def read_status(data):
    with application.app.app_context():
        submission = application.db.session.get(
            application.JobApplication,
            data["application_id"],
        )
        return submission.status, submission.updated_at


def post_status(
    client,
    data,
    token,
    target="under_review",
    expected="submitted",
):
    return client.post(
        data["update_url"],
        data={
            "csrf_token": token,
            "expected_status": expected,
            "status": target,
            "page": "1",
        },
    )


@pytest.mark.parametrize(
    ("starting", "target"),
    [
        ("submitted", "under_review"),
        ("submitted", "shortlisted"),
        ("submitted", "rejected"),
        ("under_review", "shortlisted"),
        ("under_review", "rejected"),
        ("shortlisted", "under_review"),
        ("shortlisted", "hired"),
        ("shortlisted", "rejected"),
    ],
)
def test_allowed_status_changes(
    client,
    status_data,
    starting,
    target,
):
    set_status(status_data, starting)
    sign_in(client)
    token = get_token(client, status_data)
    before = read_status(status_data)

    response = post_status(
        client,
        status_data,
        token,
        target=target,
        expected=starting,
    )

    assert response.status_code == 302
    assert status_data["list_url"] in response.headers["Location"]

    status, updated_at = read_status(status_data)
    assert status == target
    assert updated_at > before[1]

    with application.app.app_context():
        submission = application.db.session.get(
            application.JobApplication,
            status_data["application_id"],
        )
        assert submission.resume_content == b"test-resume-content"
        assert submission.resume_filename == "resume.pdf"
        assert submission.resume_text == (
            "Python developer with Flask experience."
        )
        assert submission.submitted_at == datetime(2026, 1, 1)
        assert submission.job_title_snapshot == "Python Developer"
        assert submission.job_description_snapshot == (
            "Build Python applications using Flask."
        )


@pytest.mark.parametrize(
    ("starting", "target"),
    [
        ("submitted", "hired"),
        ("submitted", "submitted"),
        ("under_review", "submitted"),
        ("shortlisted", "submitted"),
        ("rejected", "under_review"),
        ("hired", "shortlisted"),
        ("withdrawn", "under_review"),
        ("submitted", "withdrawn"),
        ("submitted", "invalid_status"),
    ],
)
def test_disallowed_status_changes(
    client,
    status_data,
    starting,
    target,
):
    set_status(status_data, starting)
    sign_in(client)
    token = get_token(client, status_data)
    before = read_status(status_data)

    response = post_status(
        client,
        status_data,
        token,
        target=target,
        expected=starting,
    )

    assert response.status_code == 400
    assert read_status(status_data) == before


def test_status_update_requires_login(client, status_data):
    before = read_status(status_data)

    response = post_status(client, status_data, "unused")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert read_status(status_data) == before


@pytest.mark.parametrize("role", ["candidate", "admin"])
def test_non_recruiter_cannot_update_status(
    client,
    status_data,
    role,
):
    with application.app.app_context():
        user = create_user(
            name="Blocked User",
            email="blocked-status@example.com",
        )
        user.role = role
        application.db.session.commit()

    sign_in(client, "blocked-status@example.com")
    before = read_status(status_data)

    response = post_status(client, status_data, "unused")

    assert response.status_code == 403
    assert read_status(status_data) == before


def test_other_recruiter_cannot_update_status(client, status_data):
    with application.app.app_context():
        user = create_user(
            name="Other Recruiter",
            email="other-status@example.com",
        )
        user.role = "recruiter"
        application.db.session.commit()

    sign_in(client, "other-status@example.com")
    before = read_status(status_data)

    response = post_status(client, status_data, "unused")

    assert response.status_code == 404
    assert read_status(status_data) == before


@pytest.mark.parametrize("token", ["", "incorrect-token"])
def test_status_update_requires_valid_csrf(
    client,
    status_data,
    token,
):
    sign_in(client)
    get_token(client, status_data)
    before = read_status(status_data)

    response = post_status(client, status_data, token)

    assert response.status_code == 400
    assert read_status(status_data) == before


def test_stale_form_cannot_overwrite_new_status(client, status_data):
    sign_in(client)
    token = get_token(client, status_data)

    first = post_status(client, status_data, token)

    assert first.status_code == 302
    saved_state = read_status(status_data)
    assert saved_state[0] == "under_review"

    stale = post_status(
        client,
        status_data,
        token,
        target="rejected",
        expected="submitted",
    )

    assert stale.status_code == 409
    assert read_status(status_data) == saved_state


def test_get_cannot_change_status(client, status_data):
    sign_in(client)
    before = read_status(status_data)

    response = client.get(
        status_data["update_url"],
        query_string={"status": "rejected"},
    )

    assert response.status_code == 405
    assert read_status(status_data) == before


def test_application_must_belong_to_url_job(client, status_data):
    sign_in(client)
    token = get_token(client, status_data)

    with application.app.app_context():
        original_job = application.db.session.get(
            application.JobPosting,
            status_data["job_id"],
        )
        other_job = application.JobPosting(
            recruiter_id=original_job.recruiter_id,
            title="Another Job",
            company="Test Company",
            location="Hyderabad",
            description="Another job description.",
            employment_type="full_time",
            status="open",
        )
        application.db.session.add(other_job)
        application.db.session.commit()
        other_job_id = other_job.id

    before = read_status(status_data)

    response = client.post(
        f"/recruiter/jobs/{other_job_id}/applications/"
        f"{status_data['application_id']}/status",
        data={
            "csrf_token": token,
            "expected_status": "submitted",
            "status": "rejected",
        },
    )

    assert response.status_code == 404
    assert read_status(status_data) == before


def test_candidate_sees_updated_status(client, status_data):
    sign_in(client)
    token = get_token(client, status_data)

    response = post_status(
        client,
        status_data,
        token,
        target="shortlisted",
    )

    assert response.status_code == 302

    # Use a separate browser session for the candidate.
    with application.app.test_client() as candidate_client:
        sign_in(candidate_client, "status-candidate@example.com")

        response = candidate_client.get("/candidate/applications")

        assert response.status_code == 200
        assert b"Shortlisted" in response.data


def test_terminal_status_has_no_update_form(client, status_data):
    set_status(status_data, "hired")
    sign_in(client)

    response = client.get(status_data["list_url"])

    assert response.status_code == 200
    assert b"No further recruiter status changes" in response.data
    assert b'name="expected_status"' not in response.data