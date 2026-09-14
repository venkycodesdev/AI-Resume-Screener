from io import BytesIO
from urllib.parse import urlsplit

import pytest
from docx import Document
from reportlab.pdfgen import canvas
from sqlalchemy.exc import IntegrityError

from test_v2 import application, create_user


@pytest.fixture
def application_setup(client):
    with application.app.app_context():
        candidate = create_user(
            name="Application Candidate",
            email="applicant@example.com",
        )
        candidate.role = "candidate"

        recruiter = create_user(
            name="Application Recruiter",
            email="application-recruiter@example.com",
        )
        recruiter.role = "recruiter"

        job = application.JobPosting(
            recruiter_id=recruiter.id,
            title="Python Developer",
            company="Demo Company",
            location="Hyderabad",
            description="Build Python and Flask applications.",
            employment_type="full_time",
            status="open",
        )
        application.db.session.add(job)
        application.db.session.commit()

        return {
            "candidate_id": candidate.id,
            "job_id": job.id,
            "url": f"/candidate/jobs/{job.id}/apply",
        }


def sign_in(client, email="applicant@example.com"):
    response = client.post(
        "/login",
        data={"email": email, "password": "Password123"},
    )
    assert response.status_code == 302


def resume_bytes(extension="pdf", text="Python developer with Flask skills."):
    buffer = BytesIO()

    if extension == "pdf":
        document = canvas.Canvas(buffer)
        if text:
            document.drawString(72, 750, text)
        document.showPage()
        document.save()
    else:
        document = Document()
        document.add_paragraph(text)
        document.save(buffer)

    return buffer.getvalue()


def get_token(client, url):
    response = client.get(url)
    assert response.status_code == 200

    with client.session_transaction() as session:
        return session["application_csrf_token"]


def submit_resume(client, url, token, content, filename="resume.pdf"):
    return client.post(
        url,
        data={
            "csrf_token": token,
            "resume": (BytesIO(content), filename),
        },
        content_type="multipart/form-data",
    )


@pytest.mark.parametrize("method", ["get", "post"])
def test_application_requires_login(client, application_setup, method):
    response = getattr(client, method)(application_setup["url"])

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/login"


@pytest.mark.parametrize("role", ["recruiter", "admin"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_application_requires_candidate(
    client, application_setup, role, method
):
    with application.app.app_context():
        user = create_user(email="blocked@example.com")
        user.role = role
        application.db.session.commit()

    sign_in(client, "blocked@example.com")
    response = getattr(client, method)(application_setup["url"])

    assert response.status_code == 403


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_valid_resume_creates_application(
    client, application_setup, extension
):
    sign_in(client)
    token = get_token(client, application_setup["url"])
    content = resume_bytes(extension)

    response = submit_resume(
        client,
        application_setup["url"],
        token,
        content,
        filename=f"resume.{extension}",
    )

    assert response.status_code == 302

    with application.app.app_context():
        saved = application.JobApplication.query.one()

        assert saved.candidate_id == application_setup["candidate_id"]
        assert saved.job_id == application_setup["job_id"]
        assert saved.status == "submitted"
        assert saved.resume_content == content
        assert "Python developer" in saved.resume_text
        assert saved.job_title_snapshot == "Python Developer"
        assert saved.job_description_snapshot == (
            "Build Python and Flask applications."
        )

    confirmation = client.get(response.headers["Location"])
    assert confirmation.status_code == 200
    assert "Your application is saved." in confirmation.get_data(
        as_text=True
    )


def test_duplicate_submission_keeps_first_resume(client, application_setup):
    sign_in(client)
    url = application_setup["url"]
    token = get_token(client, url)
    original = resume_bytes(text="Original resume with Python skills.")

    first = submit_resume(client, url, token, original)
    second = submit_resume(
        client,
        url,
        token,
        resume_bytes(text="Replacement resume."),
    )

    assert first.status_code == 302
    assert second.status_code == 302
    assert first.headers["Location"] == second.headers["Location"]

    with application.app.app_context():
        saved = application.JobApplication.query.one()
        assert saved.resume_content == original


@pytest.mark.parametrize("status", ["draft", "closed"])
def test_unavailable_job_rejects_application(
    client, application_setup, status
):
    sign_in(client)
    url = application_setup["url"]
    token = get_token(client, url)

    with application.app.app_context():
        job = application.db.session.get(
            application.JobPosting,
            application_setup["job_id"],
        )
        job.status = status
        application.db.session.commit()

    assert client.get(url).status_code == 404

    response = submit_resume(client, url, token, resume_bytes())
    assert response.status_code == 404

    with application.app.app_context():
        assert application.JobApplication.query.count() == 0


@pytest.mark.parametrize(
    "filename,content",
    [
        ("resume.pdf", b""),
        ("resume.txt", b"Python developer"),
        ("resume.pdf", b"This is not a PDF"),
        ("resume.pdf", b"%PDF-" + b"x" * (10 * 1024 * 1024)),
    ],
    ids=["empty-file", "unsupported-type", "fake-pdf", "oversized-file"],
)
def test_invalid_upload_is_not_saved(
    client, application_setup, filename, content
):
    sign_in(client)
    token = get_token(client, application_setup["url"])

    response = submit_resume(
        client,
        application_setup["url"],
        token,
        content,
        filename,
    )

    assert response.status_code == 400

    with application.app.app_context():
        assert application.JobApplication.query.count() == 0


@pytest.mark.parametrize("token", ["", "incorrect-token"])
def test_submission_requires_csrf(client, application_setup, token):
    sign_in(client)
    get_token(client, application_setup["url"])

    response = submit_resume(
        client,
        application_setup["url"],
        token,
        resume_bytes(),
    )

    assert response.status_code == 400

    with application.app.app_context():
        assert application.JobApplication.query.count() == 0


def test_other_candidate_cannot_view_confirmation(client, application_setup):
    sign_in(client)
    token = get_token(client, application_setup["url"])
    response = submit_resume(
        client,
        application_setup["url"],
        token,
        resume_bytes(),
    )
    assert response.status_code == 302
    confirmation_url = response.headers["Location"]

    with application.app.app_context():
        other = create_user(email="other-applicant@example.com")
        other.role = "candidate"
        application.db.session.commit()

    client.get("/logout")
    sign_in(client, "other-applicant@example.com")

    response = client.get(confirmation_url)
    assert response.status_code == 404
    assert "resume.pdf" not in response.get_data(as_text=True)


def test_database_prevents_duplicate_applications(client, application_setup):
    sign_in(client)
    token = get_token(client, application_setup["url"])
    response = submit_resume(
        client,
        application_setup["url"],
        token,
        resume_bytes(),
    )
    assert response.status_code == 302

    with application.app.app_context():
        original = application.JobApplication.query.one()
        duplicate = application.JobApplication(
            candidate_id=original.candidate_id,
            job_id=original.job_id,
            resume_filename=original.resume_filename,
            resume_content=original.resume_content,
            resume_text=original.resume_text,
            job_title_snapshot=original.job_title_snapshot,
            job_description_snapshot=original.job_description_snapshot,
            status="submitted",
        )
        application.db.session.add(duplicate)

        with pytest.raises(IntegrityError):
            application.db.session.commit()

        application.db.session.rollback()
        assert application.JobApplication.query.count() == 1


def test_resume_without_readable_text_is_rejected(client, application_setup):
    sign_in(client)
    token = get_token(client, application_setup["url"])

    response = submit_resume(
        client,
        application_setup["url"],
        token,
        resume_bytes(text=""),
    )

    assert response.status_code == 400
    assert "No readable text was found" in response.get_data(as_text=True)

    with application.app.app_context():
        assert application.JobApplication.query.count() == 0