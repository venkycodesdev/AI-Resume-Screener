from datetime import datetime

import pytest

from test_v2 import application, create_user


@pytest.fixture
def notification_data(client):
    with application.app.app_context():
        candidate = create_user(
            name="Notification Candidate",
            email="notice-candidate@example.com",
        )
        candidate.role = "candidate"

        recruiter = create_user(
            name="Notification Recruiter",
            email="notice-recruiter@example.com",
        )
        recruiter.role = "recruiter"

        admin = create_user(
            name="Notification Admin",
            email="notice-admin@example.com",
        )
        admin.role = "admin"

        job = application.JobPosting(
            recruiter_id=recruiter.id,
            title="Python Developer",
            company="Notification Company",
            location="Hyderabad",
            description="Build Python applications with Flask.",
            employment_type="full_time",
            status="open",
        )
        application.db.session.add(job)
        application.db.session.flush()

        submission = application.JobApplication(
            candidate_id=candidate.id,
            job_id=job.id,
            resume_filename="resume.pdf",
            resume_content=b"test-resume",
            resume_text="Python and Flask developer.",
            job_title_snapshot=job.title,
            job_description_snapshot=job.description,
            status="submitted",
        )
        application.db.session.add(submission)

        access_request = application.RecruiterAccessRequest(
            user_id=candidate.id,
            company_name="Notification Company",
            company_website="",
            reason="We need recruiter access to hire Python developers.",
            status="pending",
        )
        application.db.session.add(access_request)

        own_notice = application.Notification(
            user_id=candidate.id,
            kind="application_status",
            title="Candidate notification",
            message="Only this candidate should see this message.",
        )
        other_notice = application.Notification(
            user_id=admin.id,
            kind="recruiter_access",
            title="Private admin notification",
            message="Private admin message.",
        )
        application.db.session.add_all([own_notice, other_notice])
        application.db.session.commit()

        return {
            "candidate_id": candidate.id,
            "recruiter_id": recruiter.id,
            "admin_id": admin.id,
            "job_id": job.id,
            "application_id": submission.id,
            "request_id": access_request.id,
            "own_notice_id": own_notice.id,
            "other_notice_id": other_notice.id,
        }


def sign_in(client, email="notice-candidate@example.com"):
    response = client.post(
        "/login",
        data={
            "email": email,
            "password": "Password123",
        },
    )
    assert response.status_code == 302


def get_token(client, path, session_key):
    response = client.get(path)
    assert response.status_code == 200

    with client.session_transaction() as session:
        return session[session_key]


def notification_state(notification_id):
    with application.app.app_context():
        notice = application.db.session.get(
            application.Notification,
            notification_id,
        )
        return notice.user_id, notice.message, notice.read_at


def candidate_notices(data):
    with application.app.app_context():
        notices = (
            application.Notification.query.filter_by(
                user_id=data["candidate_id"],
            )
            .order_by(application.Notification.id)
            .all()
        )
        return [
            {
                "id": notice.id,
                "kind": notice.kind,
                "title": notice.title,
                "message": notice.message,
                "read_at": notice.read_at,
            }
            for notice in notices
        ]


def status_post(client, data, token):
    return client.post(
        f"/recruiter/jobs/{data['job_id']}/applications/"
        f"{data['application_id']}/status",
        data={
            "csrf_token": token,
            "expected_status": "submitted",
            "status": "shortlisted",
            "page": "1",
        },
    )


def review_post(client, data, token, decision="approved"):
    return client.post(
        f"/admin/recruiter-requests/{data['request_id']}/review",
        data={
            "csrf_token": token,
            "decision": decision,
            "review_note": "Notification integration test.",
        },
    )


@pytest.mark.parametrize("method", ["get", "post"])
def test_notification_routes_require_login(
    client, notification_data, method
):
    path = (
        "/notifications"
        if method == "get"
        else (
            f"/notifications/"
            f"{notification_data['own_notice_id']}/read"
        )
    )

    response = getattr(client, method)(path)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


@pytest.mark.parametrize(
    "email",
    [
        "notice-candidate@example.com",
        "notice-recruiter@example.com",
        "notice-admin@example.com",
    ],
)
def test_all_roles_can_open_notifications(
    client, notification_data, email
):
    sign_in(client, email)

    response = client.get("/notifications")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"


def test_list_shows_only_own_notifications(client, notification_data):
    sign_in(client)

    response = client.get(
        "/notifications",
        query_string={"user_id": notification_data["admin_id"]},
    )

    assert response.status_code == 200
    assert b"Candidate notification" in response.data
    assert b"Private admin notification" not in response.data
    assert b"1 unread" in response.data

    # Opening the page must not mark a notification as read.
    assert notification_state(
        notification_data["own_notice_id"]
    )[2] is None


def test_mark_read_preserves_first_read_timestamp(
    client, notification_data
):
    sign_in(client)
    token = get_token(
        client, "/notifications", "notification_csrf_token"
    )
    notice_id = notification_data["own_notice_id"]
    path = f"/notifications/{notice_id}/read"

    response = client.post(path, data={"csrf_token": token})

    assert response.status_code == 302
    first_state = notification_state(notice_id)
    assert first_state[2] is not None

    response = client.post(path, data={"csrf_token": token})

    assert response.status_code == 302
    assert notification_state(notice_id) == first_state

    page = client.get("/notifications")
    assert b"0 unread" in page.data
    assert b"Mark as read" not in page.data


def test_cannot_mark_another_users_notification_read(
    client, notification_data
):
    sign_in(client)
    token = get_token(
        client, "/notifications", "notification_csrf_token"
    )
    notice_id = notification_data["other_notice_id"]
    before = notification_state(notice_id)

    response = client.post(
        f"/notifications/{notice_id}/read",
        data={"csrf_token": token},
    )

    assert response.status_code == 404
    assert notification_state(notice_id) == before


@pytest.mark.parametrize("token", ["", "wrong-token"])
def test_mark_read_requires_csrf(client, notification_data, token):
    sign_in(client)
    get_token(client, "/notifications", "notification_csrf_token")
    notice_id = notification_data["own_notice_id"]
    before = notification_state(notice_id)

    response = client.post(
        f"/notifications/{notice_id}/read",
        data={"csrf_token": token},
    )

    assert response.status_code == 400
    assert notification_state(notice_id) == before


def test_mark_read_is_post_only(client, notification_data):
    sign_in(client)
    notice_id = notification_data["own_notice_id"]

    response = client.get(f"/notifications/{notice_id}/read")

    assert response.status_code == 405
    assert notification_state(notice_id)[2] is None


@pytest.mark.parametrize("page", ["0", "-1", "abc"])
def test_invalid_notification_page(client, notification_data, page):
    sign_in(client)

    response = client.get("/notifications", query_string={"page": page})

    assert response.status_code == 400


def test_notification_pagination(client, notification_data):
    with application.app.app_context():
        # Remove only this candidate's initial notification.
        application.Notification.query.filter_by(
            user_id=notification_data["candidate_id"]
        ).delete()

        for index in range(11):
            application.db.session.add(
                application.Notification(
                    user_id=notification_data["candidate_id"],
                    kind="application_status",
                    title=f"Notice-{index:02d}",
                    message="Pagination test.",
                    created_at=datetime(2026, 1, 1),
                )
            )
        application.db.session.commit()

    sign_in(client)

    first = client.get("/notifications")
    second = client.get("/notifications?page=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert b"Notice-10" in first.data
    assert b"Notice-00" not in first.data
    assert b"Notice-00" in second.data
    assert b"Notice-10" not in second.data
    assert b"Private admin notification" not in first.data
    assert b"Private admin notification" not in second.data


def test_status_change_creates_one_candidate_notification(
    client, notification_data
):
    sign_in(client, "notice-recruiter@example.com")
    token = get_token(
        client,
        f"/recruiter/jobs/{notification_data['job_id']}/applicants",
        "application_status_csrf_token",
    )
    before = candidate_notices(notification_data)

    response = status_post(client, notification_data, token)

    assert response.status_code == 302
    after = candidate_notices(notification_data)
    assert len(after) == len(before) + 1
    assert after[-1]["kind"] == "application_status"
    assert "Python Developer" in after[-1]["message"]
    assert "Shortlisted" in after[-1]["message"]
    assert after[-1]["read_at"] is None

    # Repeating the stale form must not create another notification.
    repeated = status_post(client, notification_data, token)

    assert repeated.status_code == 409
    assert candidate_notices(notification_data) == after


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_access_decision_notifies_applicant(
    client, notification_data, decision
):
    sign_in(client, "notice-admin@example.com")
    token = get_token(
        client,
        "/admin/recruiter-requests",
        "recruiter_access_csrf_token",
    )
    before = candidate_notices(notification_data)

    response = review_post(
        client, notification_data, token, decision=decision
    )

    assert response.status_code == 302
    after = candidate_notices(notification_data)
    assert len(after) == len(before) + 1
    assert after[-1]["kind"] == "recruiter_access"
    assert decision in after[-1]["message"]
    assert "Notification integration test." in after[-1]["message"]
    assert after[-1]["read_at"] is None

    repeated = review_post(
        client, notification_data, token, decision=decision
    )
    assert repeated.status_code == 409
    assert candidate_notices(notification_data) == after

    # The notification remains accessible after a role change.
    applicant_client = application.app.test_client()
    sign_in(applicant_client)
    page = applicant_client.get("/notifications")
    assert page.status_code == 200
    assert f"Recruiter access {decision}".encode() in page.data


@pytest.mark.parametrize("operation", ["status", "access"])
def test_failed_commit_rolls_back_change_and_notification(
    client, notification_data, monkeypatch, operation
):
    if operation == "status":
        sign_in(client, "notice-recruiter@example.com")
        token = get_token(
            client,
            f"/recruiter/jobs/{notification_data['job_id']}/applicants",
            "application_status_csrf_token",
        )
    else:
        sign_in(client, "notice-admin@example.com")
        token = get_token(
            client,
            "/admin/recruiter-requests",
            "recruiter_access_csrf_token",
        )

    before = candidate_notices(notification_data)

    def fail_commit():
        # Send pending notification inserts to the database, then
        # simulate failure before the transaction is committed.
        application.db.session.flush()
        raise RuntimeError("Simulated commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(application.db.session, "commit", fail_commit)

        with pytest.raises(RuntimeError, match="Simulated commit failure"):
            if operation == "status":
                status_post(client, notification_data, token)
            else:
                review_post(client, notification_data, token)

    assert candidate_notices(notification_data) == before

    with application.app.app_context():
        submission = application.db.session.get(
            application.JobApplication,
            notification_data["application_id"],
        )
        access_request = application.db.session.get(
            application.RecruiterAccessRequest,
            notification_data["request_id"],
        )
        candidate = application.db.session.get(
            application.User,
            notification_data["candidate_id"],
        )

        assert submission.status == "submitted"
        assert access_request.status == "pending"
        assert access_request.reviewed_at is None
        assert access_request.reviewed_by_id is None
        assert candidate.role == "candidate"