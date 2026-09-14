from urllib.parse import urlsplit

import pytest

from test_v2 import application, create_user


@pytest.fixture
def recruiter_data(client):
    with application.app.app_context():
        owner = create_user(
            name="Owner Recruiter",
            email="owner-recruiter@example.com",
        )
        owner.role = "recruiter"

        other = create_user(
            name="Other Recruiter",
            email="other-recruiter@example.com",
        )
        other.role = "recruiter"

        candidate = create_user(
            name="Applicant Example",
            email="download-candidate@example.com",
        )
        candidate.role = "candidate"

        jobs = []
        submissions = []

        for recruiter, title, filename in [
            (owner, "Owner Job", "owner-resume.pdf"),
            (other, "Other Job", "private-other-resume.pdf"),
        ]:
            job = application.JobPosting(
                recruiter_id=recruiter.id,
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
                candidate_id=candidate.id,
                job_id=job.id,
                resume_filename=filename,
                resume_content=b"Stored resume test bytes",
                resume_text="Python developer.",
                job_title_snapshot=title,
                job_description_snapshot=job.description,
                status="submitted",
            )
            application.db.session.add(submission)
            application.db.session.flush()

            jobs.append(job.id)
            submissions.append(submission.id)

        application.db.session.commit()

        return {
            "owner_id": owner.id,
            "job_id": jobs[0],
            "other_job_id": jobs[1],
            "application_id": submissions[0],
            "other_application_id": submissions[1],
        }


def sign_in(client, email="owner-recruiter@example.com"):
    response = client.post(
        "/login",
        data={"email": email, "password": "Password123"},
    )
    assert response.status_code == 302


def route_for(data, page):
    job_id = data["job_id"]

    if page == "list":
        return f"/recruiter/jobs/{job_id}/applicants"

    application_id = data["application_id"]
    return (
        f"/recruiter/jobs/{job_id}/applications/"
        f"{application_id}/resume"
    )


@pytest.mark.parametrize("page", ["list", "download"])
def test_applicant_routes_require_login(client, recruiter_data, page):
    response = client.get(route_for(recruiter_data, page))

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/login"


@pytest.mark.parametrize("role", ["candidate", "admin"])
@pytest.mark.parametrize("page", ["list", "download"])
def test_applicant_routes_require_recruiter(
    client, recruiter_data, role, page
):
    with application.app.app_context():
        user = create_user(email="blocked-reviewer@example.com")
        user.role = role
        application.db.session.commit()

    sign_in(client, "blocked-reviewer@example.com")
    response = client.get(route_for(recruiter_data, page))

    assert response.status_code == 403


@pytest.mark.parametrize("page", ["list", "download"])
def test_other_recruiter_is_blocked(client, recruiter_data, page):
    sign_in(client, "other-recruiter@example.com")
    response = client.get(route_for(recruiter_data, page))

    assert response.status_code == 404
    assert b"Stored resume test bytes" not in response.data


def test_owner_sees_only_selected_job_applicants(client, recruiter_data):
    sign_in(client)
    response = client.get(route_for(recruiter_data, "list"))

    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert "Applicant Example" in html
    assert "owner-resume.pdf" in html
    assert "private-other-resume.pdf" not in html
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.parametrize(
    "extension,mimetype",
    [
        ("pdf", "application/pdf"),
        (
            "docx",
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document",
        ),
    ],
)
def test_owner_downloads_exact_resume(
    client, recruiter_data, extension, mimetype
):
    content = b"Exact stored file content for download verification"

    with application.app.app_context():
        submission = application.db.session.get(
            application.JobApplication,
            recruiter_data["application_id"],
        )
        submission.resume_filename = f"candidate.{extension}"
        submission.resume_content = content
        application.db.session.commit()

    sign_in(client)
    response = client.get(route_for(recruiter_data, "download"))

    assert response.status_code == 200
    assert response.data == content
    assert response.mimetype == mimetype

    disposition = response.headers["Content-Disposition"]
    assert disposition.startswith("attachment;")
    assert f"candidate.{extension}" in disposition
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_application_id_must_belong_to_job(client, recruiter_data):
    sign_in(client)

    # Pair an owned job with another job's application ID.
    response = client.get(
        f"/recruiter/jobs/{recruiter_data['job_id']}/applications/"
        f"{recruiter_data['other_application_id']}/resume"
    )

    assert response.status_code == 404
    assert b"Stored resume test bytes" not in response.data


@pytest.mark.parametrize("missing", ["job", "application"])
def test_missing_records_return_404(client, recruiter_data, missing):
    sign_in(client)

    if missing == "job":
        url = "/recruiter/jobs/999999/applicants"
    else:
        url = (
            f"/recruiter/jobs/{recruiter_data['job_id']}/"
            "applications/999999/resume"
        )

    assert client.get(url).status_code == 404


@pytest.mark.parametrize("page", ["abc", "0", "-1"])
def test_invalid_applicant_page_returns_400(client, recruiter_data, page):
    sign_in(client)

    response = client.get(
        route_for(recruiter_data, "list"),
        query_string={"page": page},
    )

    assert response.status_code == 400


def test_job_without_applicants_shows_empty_state(client, recruiter_data):
    with application.app.app_context():
        job = application.JobPosting(
            recruiter_id=recruiter_data["owner_id"],
            title="Empty Job",
            company="Demo Company",
            location="Hyderabad",
            description="Python position.",
            employment_type="full_time",
            status="open",
        )
        application.db.session.add(job)
        application.db.session.commit()
        job_id = job.id

    sign_in(client)
    response = client.get(f"/recruiter/jobs/{job_id}/applicants")

    assert response.status_code == 200
    assert "No applications yet" in response.get_data(as_text=True)