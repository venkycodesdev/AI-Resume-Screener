import json
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "automated-test-secret"

import pytest

import app as application


@pytest.fixture(autouse=True)
def clean_database():
    application.app.config.update(TESTING=True)
    with application.app.app_context():
        application.db.drop_all()
        application.db.create_all()
        yield
        application.db.session.remove()
        application.db.drop_all()


@pytest.fixture
def client():
    return application.app.test_client()


def create_user(name="Test User", email="test@example.com"):
    user = application.User(name=name, email=email)
    user.set_password("Password123")
    application.db.session.add(user)
    application.db.session.commit()
    return user


def login(client, email="test@example.com"):
    return client.post(
        "/login",
        data={"email": email, "password": "Password123"},
        follow_redirects=True,
    )


def create_analysis(user, filename="candidate.pdf"):
    resume_text = """PROFESSIONAL SUMMARY
Python developer building Flask REST APIs.

EXPERIENCE
- Created a Flask API with PostgreSQL.

PROJECTS
- Made an AI resume screening project using Python.

EDUCATION
B.Tech Artificial Intelligence and Machine Learning
"""
    job = "Python Flask developer with REST API, PostgreSQL, Git and AWS skills."
    resume_skills = application.extract_skills(resume_text)
    job_skills = application.extract_skills(job)
    matching = sorted(set(resume_skills) & set(job_skills))
    missing = sorted(set(job_skills) - set(resume_skills))
    breakdown = application.calculate_score_breakdown(
        resume_text, job, matching, job_skills
    )
    analysis = application.Analysis(
        user_id=user.id,
        resume_filename=filename,
        analysis_type="single",
        job_description=job,
        match_score=application.V2.weighted_score(breakdown, {"skills": 40, "experience": 30, "projects": 20, "education": 10}),
        detected_skills=json.dumps(resume_skills),
        matching_skills=json.dumps(matching),
        missing_skills=json.dumps(missing),
        interview_questions="{}",
        score_breakdown=json.dumps(breakdown),
    )
    application.db.session.add(analysis)
    application.db.session.flush()
    explanations = application.V2.build_explanations(
        resume_text, job, breakdown, matching, missing
    )
    application.V2.save_analysis_context(
        analysis, resume_text, explanations,
        {"skills": 40, "experience": 30, "projects": 20, "education": 10},
    )
    application.db.session.commit()
    return analysis


def test_v2_pages_require_login(client):
    for url in ("/reports", "/scoring-weights", "/rewrite/1"):
        response = client.get(url)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_saved_reports_are_isolated_by_user(client):
    with application.app.app_context():
        owner = create_user()
        other = create_user("Other User", "other@example.com")
        other_analysis = create_analysis(other, "private.pdf")
        private_id = other_analysis.id
    login(client)
    download = client.get(f"/reports/{private_id}/download")
    delete = client.post(f"/reports/{private_id}/delete")
    # The app's global 404 handler redirects to a safe page. It must never
    # return another user's PDF or delete their record.
    assert download.status_code == 302
    assert download.mimetype != "application/pdf"
    assert delete.status_code == 302
    with application.app.app_context():
        assert application.db.session.get(application.Analysis, private_id) is not None


def test_saved_report_search_and_pdf_download(client):
    with application.app.app_context():
        user = create_user()
        analysis = create_analysis(user, "python-developer.pdf")
        analysis_id = analysis.id
    login(client)
    response = client.get("/reports?q=python&min_score=0&type=single")
    assert response.status_code == 200
    assert b"python-developer.pdf" in response.data
    pdf = client.get(f"/reports/{analysis_id}/download")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")


def test_scoring_weights_validation_and_save(client):
    with application.app.app_context():
        create_user()
    login(client)
    invalid = client.post(
        "/scoring-weights",
        data={"skills": 50, "experience": 30, "projects": 20, "education": 10},
    )
    assert invalid.status_code == 200
    assert b"total must equal 100" in invalid.data
    valid = client.post(
        "/scoring-weights",
        data={"skills": 35, "experience": 35, "projects": 20, "education": 10},
        follow_redirects=True,
    )
    assert valid.status_code == 200
    assert b"Scoring weights saved" in valid.data
    with application.app.app_context():
        preference = application.V2.models["ScoringPreference"].query.one()
        assert json.loads(preference.weights)["skills"] == 35


def test_resume_rewrite_edit_download_and_reanalyze(client):
    with application.app.app_context():
        user = create_user()
        analysis = create_analysis(user)
        analysis_id = analysis.id
    login(client)
    page = client.get(f"/rewrite/{analysis_id}")
    assert page.status_code == 200
    assert b"Resume Rewriter" in page.data
    generated = client.post(
        f"/rewrite/{analysis_id}", data={"action": "generate", "tone": "technical"},
        follow_redirects=True,
    )
    assert generated.status_code == 200
    assert b"Developed" in generated.data
    with application.app.app_context():
        rewrite = application.V2.models["ResumeRewrite"].query.one()
        rewrite_id = rewrite.id
    for file_format, mimetype in (
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("pdf", "application/pdf"),
    ):
        download = client.get(f"/rewrite/{rewrite_id}/download/{file_format}")
        assert download.status_code == 200
        assert download.mimetype == mimetype
    result = client.post(f"/rewrite/{rewrite_id}/reanalyze")
    assert result.status_code == 200
    assert b"RE-ANALYSIS COMPLETE" in result.data
    with application.app.app_context():
        assert application.Analysis.query.count() == 2


def test_weighted_score_uses_recruiter_values():
    score = application.V2.weighted_score(
        {"skills": 100, "experience": 50, "projects": 0, "education": 0},
        {"skills": 50, "experience": 50, "projects": 0, "education": 0},
    )
    assert score == 75
