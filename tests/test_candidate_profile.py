import pytest

from test_v2 import application, create_user


PROFILE_URL = "/candidate/profile"


@pytest.fixture
def profile_user(client):
    with application.app.app_context():
        user = create_user(
            name="Profile Candidate",
            email="profile-candidate@example.com",
        )
        user.role = "candidate"
        application.db.session.commit()
        return user.id


def sign_in(client, email="profile-candidate@example.com"):
    response = client.post(
        "/login",
        data={
            "email": email,
            "password": "Password123",
        },
    )
    assert response.status_code == 302


def get_token(client):
    response = client.get(PROFILE_URL)
    assert response.status_code == 200

    with client.session_transaction() as session:
        return session["candidate_profile_csrf_token"]


def valid_values():
    return {
        "headline": "Python Developer",
        "bio": "B.Tech student building Flask applications.",
        "location": "Hyderabad",
        "skills": "Python, Flask, SQL",
        "education": "B.Tech Artificial Intelligence and Machine Learning",
        "graduation_year": "2028",
        "github_url": "https://github.com/example",
        "linkedin_url": "https://www.linkedin.com/in/example",
        "portfolio_url": "https://example.com",
    }


def save_profile(client, token, values=None):
    data = valid_values() if values is None else values.copy()
    data["csrf_token"] = token
    return client.post(PROFILE_URL, data=data)


def profile_state(user_id):
    with application.app.app_context():
        profile = application.CandidateProfile.query.filter_by(
            user_id=user_id,
        ).first()

        if profile is None:
            return None

        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "headline": profile.headline,
            "bio": profile.bio,
            "location": profile.location,
            "skills": profile.skills,
            "education": profile.education,
            "graduation_year": profile.graduation_year,
            "github_url": profile.github_url,
            "linkedin_url": profile.linkedin_url,
            "portfolio_url": profile.portfolio_url,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }


@pytest.mark.parametrize("method", ["get", "post"])
def test_profile_requires_login(client, profile_user, method):
    response = getattr(client, method)(PROFILE_URL)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert profile_state(profile_user) is None


@pytest.mark.parametrize("role", ["recruiter", "admin"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_profile_requires_candidate(
    client, profile_user, role, method
):
    with application.app.app_context():
        user = application.db.session.get(
            application.User, profile_user
        )
        user.role = role
        application.db.session.commit()

    sign_in(client)
    response = getattr(client, method)(PROFILE_URL)

    assert response.status_code == 403
    assert profile_state(profile_user) is None


def test_get_does_not_create_profile(client, profile_user):
    sign_in(client)

    response = client.get(PROFILE_URL)

    assert response.status_code == 200
    assert b"My Profile" in response.data
    assert response.headers["Cache-Control"] == "private, no-store"
    assert profile_state(profile_user) is None


def test_candidate_dashboard_links_to_profile(client, profile_user):
    sign_in(client)

    response = client.get("/candidate/dashboard")

    assert response.status_code == 200
    assert b'href="/candidate/profile"' in response.data


def test_save_and_reload_profile(client, profile_user):
    sign_in(client)
    token = get_token(client)

    response = save_profile(client, token)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(PROFILE_URL)

    saved = profile_state(profile_user)
    assert saved["user_id"] == profile_user

    for key, value in valid_values().items():
        expected = int(value) if key == "graduation_year" else value
        assert saved[key] == expected

    response = client.get(PROFILE_URL)
    assert response.status_code == 200
    assert b"Python Developer" in response.data
    assert b"https://github.com/example" in response.data
    assert b"Your profile has been saved." in response.data


def test_edit_updates_existing_profile(client, profile_user):
    sign_in(client)
    token = get_token(client)
    assert save_profile(client, token).status_code == 302
    before = profile_state(profile_user)

    values = valid_values()
    values["headline"] = "Backend Developer"
    values["location"] = "Bengaluru"

    response = save_profile(client, token, values)

    assert response.status_code == 302
    after = profile_state(profile_user)
    assert after["id"] == before["id"]
    assert after["created_at"] == before["created_at"]
    assert after["headline"] == "Backend Developer"
    assert after["location"] == "Bengaluru"

    with application.app.app_context():
        assert application.CandidateProfile.query.filter_by(
            user_id=profile_user
        ).count() == 1


def test_optional_fields_can_be_cleared(client, profile_user):
    sign_in(client)
    token = get_token(client)
    assert save_profile(client, token).status_code == 302

    response = save_profile(client, token, {})

    assert response.status_code == 302
    saved = profile_state(profile_user)

    for key in valid_values():
        expected = None if key == "graduation_year" else ""
        assert saved[key] == expected


@pytest.mark.parametrize("token", ["", "incorrect-token"])
def test_invalid_csrf_preserves_profile(client, profile_user, token):
    sign_in(client)
    correct_token = get_token(client)
    assert save_profile(client, correct_token).status_code == 302
    before = profile_state(profile_user)

    values = valid_values()
    values["headline"] = "Unauthorized change"
    response = save_profile(client, token, values)

    assert response.status_code == 400
    assert profile_state(profile_user) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("headline", "x" * 151),
        ("bio", "x" * 2001),
        ("location", "x" * 151),
        ("skills", "x" * 2001),
        ("education", "x" * 256),
        ("github_url", "https://github.com/" + "x" * 500),
        ("linkedin_url", "https://linkedin.com/" + "x" * 500),
        ("portfolio_url", "https://example.com/" + "x" * 500),
        ("graduation_year", "1899"),
        ("graduation_year", "2101"),
        ("graduation_year", "2028.5"),
        ("graduation_year", "abcd"),
        ("github_url", "https://github.com.evil.example/user"),
        ("linkedin_url", "https://example.com/in/user"),
        ("portfolio_url", "javascript:alert(1)"),
        ("portfolio_url", "http://example.com"),
        ("portfolio_url", "https://user:password@example.com"),
        ("portfolio_url", "https://example.com:invalid"),
        ("portfolio_url", "https://example.com/my portfolio"),
    ],
    ids=[
        "long-headline",
        "long-bio",
        "long-location",
        "long-skills",
        "long-education",
        "long-github",
        "long-linkedin",
        "long-portfolio",
        "year-too-early",
        "year-too-late",
        "decimal-year",
        "nonnumeric-year",
        "fake-github-host",
        "wrong-linkedin-host",
        "javascript-url",
        "http-url",
        "url-credentials",
        "invalid-port",
        "url-whitespace",
    ],
)
def test_invalid_input_preserves_saved_profile(
    client, profile_user, field, value
):
    sign_in(client)
    token = get_token(client)
    assert save_profile(client, token).status_code == 302
    before = profile_state(profile_user)

    values = valid_values()
    values[field] = value

    response = save_profile(client, token, values)

    assert response.status_code == 400
    assert b"Your profile was not saved." in response.data
    assert profile_state(profile_user) == before


def test_candidate_cannot_edit_another_profile(client, profile_user):
    with application.app.app_context():
        other = create_user(
            name="Other Candidate",
            email="other-profile@example.com",
        )
        other.role = "candidate"
        application.db.session.flush()

        other_profile = application.CandidateProfile(
            user_id=other.id,
            headline="Private other headline",
        )
        application.db.session.add(other_profile)
        application.db.session.commit()

        other_id = other.id
        other_profile_id = other_profile.id

    before_other = profile_state(other_id)
    sign_in(client)
    token = get_token(client)

    response = client.get(
        PROFILE_URL,
        query_string={"user_id": other_id},
    )
    assert response.status_code == 200
    assert b"Private other headline" not in response.data

    values = valid_values()
    values.update(
        {
            "user_id": str(other_id),
            "id": str(other_profile_id),
            "role": "admin",
            "email": "changed@example.com",
            "name": "Changed Name",
        }
    )

    response = save_profile(client, token, values)

    assert response.status_code == 302
    assert profile_state(other_id) == before_other
    assert profile_state(profile_user)["headline"] == "Python Developer"

    with application.app.app_context():
        user = application.db.session.get(
            application.User, profile_user
        )
        assert user.role == "candidate"
        assert user.email == "profile-candidate@example.com"
        assert user.name == "Profile Candidate"


def test_profile_text_is_html_escaped(client, profile_user):
    sign_in(client)
    token = get_token(client)
    values = valid_values()
    values["bio"] = "</textarea><script>alert(1)</script>"

    assert save_profile(client, token, values).status_code == 302

    response = client.get(PROFILE_URL)

    assert response.status_code == 200
    assert b"<script>alert(1)</script>" not in response.data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in response.data