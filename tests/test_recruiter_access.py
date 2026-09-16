import pytest

from test_v2 import application, create_user


CANDIDATE_URL = "/candidate/recruiter-access"
ADMIN_URL = "/admin/recruiter-requests"


@pytest.fixture
def access_users(client):
    with application.app.app_context():
        candidate = create_user(
            name="Access Candidate",
            email="access-candidate@example.com",
        )
        candidate.role = "candidate"

        admin = create_user(
            name="Access Admin",
            email="access-admin@example.com",
        )
        admin.role = "admin"

        application.db.session.commit()

        return {
            "candidate_id": candidate.id,
            "admin_id": admin.id,
        }


def sign_in(client, email="access-candidate@example.com"):
    response = client.post(
        "/login",
        data={
            "email": email,
            "password": "Password123",
        },
    )
    assert response.status_code == 302


def get_token(client, url):
    response = client.get(url)
    assert response.status_code == 200

    with client.session_transaction() as session:
        return session["recruiter_access_csrf_token"]


def request_values():
    return {
        "company_name": "Example Company",
        "company_website": "https://example.com",
        "reason": (
            "I manage hiring for our company and need to recruit "
            "Python developers and engineering interns."
        ),
    }


def create_pending(users):
    with application.app.app_context():
        submission = application.RecruiterAccessRequest(
            user_id=users["candidate_id"],
            status="pending",
            **request_values(),
        )
        application.db.session.add(submission)
        application.db.session.commit()
        return submission.id


def saved_state(users):
    with application.app.app_context():
        candidate = application.db.session.get(
            application.User,
            users["candidate_id"],
        )
        submission = (
            application.RecruiterAccessRequest.query.filter_by(
                user_id=candidate.id,
            ).first()
        )

        result = {
            "role": candidate.role,
            "request": None,
        }

        if submission is not None:
            result["request"] = {
                "id": submission.id,
                "company_name": submission.company_name,
                "company_website": submission.company_website,
                "reason": submission.reason,
                "status": submission.status,
                "reviewed_by_id": submission.reviewed_by_id,
                "reviewed_at": submission.reviewed_at,
                "review_note": submission.review_note,
            }

        return result


def review(
    client,
    request_id,
    token,
    decision="approved",
    note="Reviewed company details.",
):
    return client.post(
        f"{ADMIN_URL}/{request_id}/review",
        data={
            "csrf_token": token,
            "decision": decision,
            "review_note": note,
        },
    )


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", CANDIDATE_URL),
        ("post", CANDIDATE_URL),
        ("get", ADMIN_URL),
        ("post", f"{ADMIN_URL}/1/review"),
    ],
)
def test_access_routes_require_login(
    client,
    access_users,
    method,
    url,
):
    response = getattr(client, method)(url)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert saved_state(access_users)["request"] is None


@pytest.mark.parametrize("role", ["recruiter", "admin"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_only_candidates_can_request_access(
    client,
    access_users,
    role,
    method,
):
    with application.app.app_context():
        user = application.db.session.get(
            application.User,
            access_users["candidate_id"],
        )
        user.role = role
        application.db.session.commit()

    sign_in(client)
    response = getattr(client, method)(CANDIDATE_URL)

    assert response.status_code == 403
    assert saved_state(access_users)["request"] is None


@pytest.mark.parametrize("role", ["candidate", "recruiter"])
def test_non_admin_cannot_list_or_review_requests(
    client,
    access_users,
    role,
):
    request_id = create_pending(access_users)

    with application.app.app_context():
        user = application.db.session.get(
            application.User,
            access_users["candidate_id"],
        )
        user.role = role
        application.db.session.commit()

    sign_in(client)
    before = saved_state(access_users)

    assert client.get(ADMIN_URL).status_code == 403
    assert review(client, request_id, "unused").status_code == 403
    assert saved_state(access_users) == before


def test_opening_form_does_not_create_request(client, access_users):
    sign_in(client)

    response = client.get(CANDIDATE_URL)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert saved_state(access_users)["request"] is None


def test_candidate_submits_pending_request(client, access_users):
    sign_in(client)
    token = get_token(client, CANDIDATE_URL)
    values = request_values()

    # Submitted fields cannot assign roles, owners, or review decisions.
    values.update(
        {
            "csrf_token": token,
            "status": "approved",
            "role": "admin",
            "user_id": str(access_users["admin_id"]),
            "reviewed_by_id": str(access_users["admin_id"]),
        }
    )

    response = client.post(CANDIDATE_URL, data=values)

    assert response.status_code == 302

    state = saved_state(access_users)
    assert state["role"] == "candidate"
    assert state["request"]["status"] == "pending"
    assert state["request"]["reviewed_by_id"] is None
    assert state["request"]["reviewed_at"] is None

    page = client.get(CANDIDATE_URL)
    assert page.status_code == 200
    assert b"Pending" in page.data
    assert b"Example Company" in page.data


def test_duplicate_request_is_blocked(client, access_users):
    create_pending(access_users)
    sign_in(client)
    token = get_token(client, CANDIDATE_URL)
    before = saved_state(access_users)

    response = client.post(
        CANDIDATE_URL,
        data={
            **request_values(),
            "csrf_token": token,
        },
    )

    assert response.status_code == 409
    assert saved_state(access_users) == before

    with application.app.app_context():
        assert application.RecruiterAccessRequest.query.count() == 1


@pytest.mark.parametrize("token", ["", "wrong-token"])
def test_submission_requires_csrf(client, access_users, token):
    sign_in(client)
    get_token(client, CANDIDATE_URL)

    response = client.post(
        CANDIDATE_URL,
        data={
            **request_values(),
            "csrf_token": token,
        },
    )

    assert response.status_code == 400
    assert saved_state(access_users)["request"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("company_name", ""),
        ("company_name", "x" * 151),
        ("reason", "Too short"),
        ("reason", "x" * 2001),
        ("company_website", "javascript:alert(1)"),
        ("company_website", "http://example.com"),
        ("company_website", "https://user:pass@example.com"),
    ],
    ids=[
        "empty-company",
        "long-company",
        "short-reason",
        "long-reason",
        "javascript-website",
        "http-website",
        "website-credentials",
    ],
)
def test_invalid_submission_is_not_saved(
    client,
    access_users,
    field,
    value,
):
    sign_in(client)
    token = get_token(client, CANDIDATE_URL)

    values = request_values()
    values[field] = value
    values["csrf_token"] = token

    response = client.post(CANDIDATE_URL, data=values)

    assert response.status_code == 400
    assert saved_state(access_users)["request"] is None


def test_approval_changes_role_and_records_reviewer(
    client,
    access_users,
):
    request_id = create_pending(access_users)

    # Do not wrap either client in "with app.test_client()".
    # Each request must finish its context before another client runs.
    candidate_client = application.app.test_client()
    admin_client = application.app.test_client()

    sign_in(candidate_client)

    before = candidate_client.get("/dashboard")
    assert before.status_code == 302
    assert before.headers["Location"].endswith(
        "/candidate/dashboard"
    )

    sign_in(admin_client, "access-admin@example.com")
    token = get_token(admin_client, ADMIN_URL)

    response = review(admin_client, request_id, token)

    assert response.status_code == 302

    state = saved_state(access_users)
    assert state["role"] == "recruiter"
    assert state["request"]["status"] == "approved"
    assert state["request"]["reviewed_by_id"] == access_users["admin_id"]
    assert state["request"]["reviewed_at"] is not None
    assert state["request"]["review_note"] == "Reviewed company details."

    # Check the original candidate session without logging in again.
    dashboard = candidate_client.get("/dashboard")

    assert dashboard.status_code == 302, dashboard.headers
    assert dashboard.headers["Location"].endswith(
        "/recruiter/dashboard"
    ), dashboard.headers["Location"]

    assert candidate_client.get(
        "/recruiter/dashboard"
    ).status_code == 200

    assert candidate_client.get(ADMIN_URL).status_code == 403


def test_rejection_preserves_candidate_access(client, access_users):
    request_id = create_pending(access_users)

    admin_client = application.app.test_client()
    candidate_client = application.app.test_client()

    sign_in(admin_client, "access-admin@example.com")
    token = get_token(admin_client, ADMIN_URL)

    response = review(
        admin_client,
        request_id,
        token,
        decision="rejected",
        note="Please provide verifiable company information.",
    )

    assert response.status_code == 302

    state = saved_state(access_users)
    assert state["role"] == "candidate"
    assert state["request"]["status"] == "rejected"
    assert state["request"]["reviewed_by_id"] == access_users["admin_id"]
    assert state["request"]["reviewed_at"] is not None

    sign_in(candidate_client)

    page = candidate_client.get(CANDIDATE_URL)
    assert page.status_code == 200
    assert b"Please provide verifiable company information." in page.data

    assert candidate_client.get(
        "/candidate/dashboard"
    ).status_code == 200


@pytest.mark.parametrize("token", ["", "wrong-token"])
def test_review_requires_csrf(client, access_users, token):
    request_id = create_pending(access_users)
    sign_in(client, "access-admin@example.com")
    get_token(client, ADMIN_URL)
    before = saved_state(access_users)

    response = review(client, request_id, token)

    assert response.status_code == 400
    assert saved_state(access_users) == before


@pytest.mark.parametrize(
    ("decision", "note"),
    [
        ("pending", "Invalid decision."),
        ("rejected", ""),
        ("approved", "x" * 2001),
    ],
    ids=[
        "invalid-decision",
        "rejection-without-note",
        "long-note",
    ],
)
def test_invalid_review_does_not_change_request(
    client,
    access_users,
    decision,
    note,
):
    request_id = create_pending(access_users)
    sign_in(client, "access-admin@example.com")
    token = get_token(client, ADMIN_URL)
    before = saved_state(access_users)

    response = review(
        client,
        request_id,
        token,
        decision=decision,
        note=note,
    )

    assert response.status_code == 400
    assert saved_state(access_users) == before


@pytest.mark.parametrize("first_decision", ["approved", "rejected"])
def test_review_cannot_be_repeated(
    client,
    access_users,
    first_decision,
):
    request_id = create_pending(access_users)
    sign_in(client, "access-admin@example.com")
    token = get_token(client, ADMIN_URL)

    first = review(
        client,
        request_id,
        token,
        decision=first_decision,
    )
    assert first.status_code == 302
    before = saved_state(access_users)

    second_decision = (
        "rejected"
        if first_decision == "approved"
        else "approved"
    )

    response = review(
        client,
        request_id,
        token,
        decision=second_decision,
    )

    assert response.status_code == 409
    assert saved_state(access_users) == before


def test_admin_cannot_review_own_request(client, access_users):
    with application.app.app_context():
        submission = application.RecruiterAccessRequest(
            user_id=access_users["admin_id"],
            status="pending",
            **request_values(),
        )
        application.db.session.add(submission)
        application.db.session.commit()
        request_id = submission.id

    sign_in(client, "access-admin@example.com")
    token = get_token(client, ADMIN_URL)

    response = review(client, request_id, token)

    assert response.status_code == 403

    with application.app.app_context():
        submission = application.db.session.get(
            application.RecruiterAccessRequest,
            request_id,
        )
        assert submission.status == "pending"
        assert submission.reviewed_by_id is None
        assert submission.reviewed_at is None


def test_changed_applicant_role_blocks_review(client, access_users):
    request_id = create_pending(access_users)

    with application.app.app_context():
        applicant = application.db.session.get(
            application.User,
            access_users["candidate_id"],
        )
        applicant.role = "recruiter"
        application.db.session.commit()

    sign_in(client, "access-admin@example.com")
    token = get_token(client, ADMIN_URL)
    before = saved_state(access_users)

    response = review(client, request_id, token)

    assert response.status_code == 409
    assert saved_state(access_users) == before


def test_candidates_cannot_read_other_requests(client, access_users):
    create_pending(access_users)

    with application.app.app_context():
        other = create_user(
            name="Other Candidate",
            email="other-access@example.com",
        )
        other.role = "candidate"
        application.db.session.commit()

    sign_in(client, "other-access@example.com")

    response = client.get(
        CANDIDATE_URL,
        query_string={
            "user_id": access_users["candidate_id"],
        },
    )

    assert response.status_code == 200
    assert b"Example Company" not in response.data
    assert b"Submit request" in response.data


def test_review_is_post_only(client, access_users):
    request_id = create_pending(access_users)
    sign_in(client, "access-admin@example.com")
    before = saved_state(access_users)

    response = client.get(
        f"{ADMIN_URL}/{request_id}/review"
    )

    assert response.status_code == 405
    assert saved_state(access_users) == before