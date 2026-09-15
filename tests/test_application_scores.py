from datetime import datetime, timedelta
from urllib.parse import urlsplit

import pytest
from flask import template_rendered

import application_score_routes as score_routes
from application_scoring import APPLICATION_WEIGHTS, SCORING_VERSION
from test_v2 import application, create_user


@pytest.fixture
def scoring_data(client):
    with application.app.app_context():
        owner = create_user(
            name="Scoring Recruiter",
            email="scoring-owner@example.com",
        )
        owner.role = "recruiter"

        other = create_user(
            name="Other Recruiter",
            email="scoring-other@example.com",
        )
        other.role = "recruiter"

        candidate = create_user(
            name="Scoring Candidate",
            email="scoring-candidate@example.com",
        )
        candidate.role = "candidate"

        job = application.JobPosting(
            recruiter_id=owner.id,
            title="Python Developer",
            company="Demo Company",
            location="Hyderabad",
            description="Python Flask developer with PostgreSQL and Git.",
            employment_type="full_time",
            status="open",
        )
        application.db.session.add(job)
        application.db.session.flush()

        submission = application.JobApplication(
            candidate_id=candidate.id,
            job_id=job.id,
            resume_filename="resume.pdf",
            resume_content=b"Stored resume fixture",
            resume_text=(
                "PROFESSIONAL SUMMARY\nPython developer.\n"
                "PROJECTS\nBuilt a Flask application using PostgreSQL.\n"
                "EDUCATION\nB.Tech Computer Science."
            ),
            job_title_snapshot=job.title,
            job_description_snapshot=job.description,
            status="submitted",
        )
        application.db.session.add(submission)
        application.db.session.commit()

        return {
            "owner_id": owner.id,
            "job_id": job.id,
            "application_id": submission.id,
            "url": f"/recruiter/jobs/{job.id}/scores",
        }


def sign_in(client, email="scoring-owner@example.com"):
    response = client.post(
        "/login",
        data={"email": email, "password": "Password123"},
    )
    assert response.status_code == 302


def get_token(client, url):
    response = client.get(url)
    assert response.status_code == 200

    with client.session_transaction() as session:
        return session["scoring_csrf_token"]


def fake_result(value=75):
    return {
        "overall_score": value,
        "score_breakdown": {
            "skills": value,
            "experience": value,
            "projects": value,
            "education": value,
        },
        "weights": APPLICATION_WEIGHTS.copy(),
        "matching_skills": ["Python"],
        "missing_skills": ["AWS"],
        "explanations": {},
        "scoring_version": SCORING_VERSION,
    }


@pytest.mark.parametrize("method", ["get", "post"])
def test_scoring_requires_login(client, scoring_data, method):
    response = getattr(client, method)(scoring_data["url"])

    assert response.status_code == 302
    assert urlsplit(response.headers["Location"]).path == "/login"


@pytest.mark.parametrize("role", ["candidate", "admin"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_scoring_requires_recruiter(client, scoring_data, role, method):
    with application.app.app_context():
        user = create_user(email="scoring-blocked@example.com")
        user.role = role
        application.db.session.commit()

    sign_in(client, "scoring-blocked@example.com")

    response = getattr(client, method)(scoring_data["url"])
    assert response.status_code == 403

    with application.app.app_context():
        assert application.ApplicationScore.query.count() == 0


@pytest.mark.parametrize("method", ["get", "post"])
def test_other_recruiter_cannot_score(client, scoring_data, method):
    sign_in(client, "scoring-other@example.com")

    response = getattr(client, method)(scoring_data["url"])
    assert response.status_code == 404

    with application.app.app_context():
        assert application.ApplicationScore.query.count() == 0


@pytest.mark.parametrize("token", ["", "incorrect-token"])
def test_scoring_requires_csrf(client, scoring_data, token):
    sign_in(client)
    get_token(client, scoring_data["url"])

    response = client.post(
        scoring_data["url"],
        data={"csrf_token": token},
    )

    assert response.status_code == 400

    with application.app.app_context():
        assert application.ApplicationScore.query.count() == 0


def test_get_does_not_calculate_scores(client, scoring_data):
    sign_in(client)
    response = client.get(scoring_data["url"])

    assert response.status_code == 200
    assert "Not scored" in response.get_data(as_text=True)

    with application.app.app_context():
        assert application.ApplicationScore.query.count() == 0


def test_real_scoring_saves_results(client, scoring_data):
    sign_in(client)
    token = get_token(client, scoring_data["url"])

    response = client.post(
        scoring_data["url"],
        data={"csrf_token": token},
    )

    assert response.status_code == 302

    with application.app.app_context():
        saved = application.ApplicationScore.query.one()

        assert saved.application_id == scoring_data["application_id"]
        assert saved.scored_by_id == scoring_data["owner_id"]
        assert 0 <= saved.overall_score <= 100
        assert saved.weights == APPLICATION_WEIGHTS
        assert saved.scoring_version == SCORING_VERSION
        assert "Python" in saved.matching_skills
        assert set(saved.score_breakdown) == {
            "skills", "experience", "projects", "education"
        }

        submission = application.db.session.get(
            application.JobApplication,
            scoring_data["application_id"],
        )
        assert submission.status == "submitted"

    page = client.get(response.headers["Location"])
    assert page.status_code == 200
    assert "Not scored" not in page.get_data(as_text=True)


def test_refresh_updates_existing_score(client, scoring_data, monkeypatch):
    sign_in(client)
    token = get_token(client, scoring_data["url"])

    monkeypatch.setattr(
        score_routes,
        "build_application_score",
        lambda **kwargs: fake_result(60),
    )
    first = client.post(
        scoring_data["url"],
        data={"csrf_token": token},
    )
    assert first.status_code == 302

    with application.app.app_context():
        original_id = application.ApplicationScore.query.one().id

    monkeypatch.setattr(
        score_routes,
        "build_application_score",
        lambda **kwargs: fake_result(80),
    )
    second = client.post(
        scoring_data["url"],
        data={"csrf_token": token},
    )
    assert second.status_code == 302

    with application.app.app_context():
        saved = application.ApplicationScore.query.one()
        assert saved.id == original_id
        assert saved.overall_score == 80


def test_scoring_uses_saved_job_description(
    client, scoring_data, monkeypatch
):
    with application.app.app_context():
        submission = application.db.session.get(
            application.JobApplication,
            scoring_data["application_id"],
        )
        saved_description = submission.job_description_snapshot

        job = application.db.session.get(
            application.JobPosting,
            scoring_data["job_id"],
        )
        job.description = "A completely different Java position."
        application.db.session.commit()

    captured = []

    def capture_score(**kwargs):
        captured.append(kwargs["job_description"])
        return fake_result()

    monkeypatch.setattr(
        score_routes,
        "build_application_score",
        capture_score,
    )

    sign_in(client)
    token = get_token(client, scoring_data["url"])
    response = client.post(
        scoring_data["url"],
        data={"csrf_token": token},
    )

    assert response.status_code == 302
    assert captured == [saved_description]


def test_scoring_failure_preserves_previous_score(
    client, scoring_data, monkeypatch
):
    sign_in(client)
    token = get_token(client, scoring_data["url"])

    monkeypatch.setattr(
        score_routes,
        "build_application_score",
        lambda **kwargs: fake_result(65),
    )
    response = client.post(
        scoring_data["url"],
        data={"csrf_token": token},
    )
    assert response.status_code == 302

    def fail_score(**kwargs):
        raise ValueError("Test scoring failure")

    monkeypatch.setattr(
        score_routes,
        "build_application_score",
        fail_score,
    )

    response = client.post(
        scoring_data["url"],
        data={"csrf_token": token},
    )

    assert response.status_code == 400

    with application.app.app_context():
        saved = application.ApplicationScore.query.one()
        assert saved.overall_score == 65


def test_scores_sort_descending_with_unscored_last(client, scoring_data):
    with application.app.app_context():
        first = application.db.session.get(
            application.JobApplication,
            scoring_data["application_id"],
        )
        first.submitted_at = datetime(2026, 1, 1)

        submissions = [first]

        for index in range(3):
            candidate = application.User(
                name=f"Ranking Candidate {index}",
                email=f"ranking-{index}@example.com",
                password_hash="unused-test-fixture",
                role="candidate",
            )
            application.db.session.add(candidate)
            application.db.session.flush()

            submission = application.JobApplication(
                candidate_id=candidate.id,
                job_id=scoring_data["job_id"],
                resume_filename="resume.pdf",
                resume_content=b"Fixture",
                resume_text="Python developer.",
                job_title_snapshot="Python Developer",
                job_description_snapshot=first.job_description_snapshot,
                status="submitted",
                submitted_at=datetime(2026, 1, 1) + timedelta(
                    days=index + 1
                ),
            )
            application.db.session.add(submission)
            application.db.session.flush()
            submissions.append(submission)

        # Two equal high scores, one lower score and one unscored.
        for submission, value in zip(submissions[:3], [50, 90, 90]):
            application.db.session.add(
                application.ApplicationScore(
                    application_id=submission.id,
                    scored_by_id=scoring_data["owner_id"],
                    **fake_result(value),
                )
            )

        application.db.session.commit()

        expected_order = [
            submissions[1].id,
            submissions[2].id,
            submissions[0].id,
            submissions[3].id,
        ]

    captured = []

    def capture(sender, template, context, **extra):
        captured.append(context)

    sign_in(client)

    with template_rendered.connected_to(capture, application.app):
        response = client.get(scoring_data["url"])

    assert response.status_code == 200
    actual_order = [
        item.id for item in captured[-1]["pagination"].items
    ]
    assert actual_order == expected_order