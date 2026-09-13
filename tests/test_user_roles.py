from tests.test_v2 import application, clean_database, client
from sqlalchemy.exc import IntegrityError
import pytest


def test_registration_always_creates_candidate(client):
    response = client.post(
        "/register",
        data={
            "name": "Role Test",
            "email": "role-test@example.com",
            "password": "TestPassword123!",
            "confirm_password": "TestPassword123!",
            "terms": "on",
            "role": "admin",
        },
    )

    assert response.status_code == 302

    with application.app.app_context():
        user = application.User.query.filter_by(
            email="role-test@example.com"
        ).one()
        assert user.role == "candidate"


def test_database_rejects_invalid_role(client):
    with application.app.app_context():
        user = application.User(
            name="Invalid Role",
            email="invalid-role@example.com",
            role="superuser",
        )
        user.set_password("TestPassword123!")
        application.db.session.add(user)

        with pytest.raises(IntegrityError):
            application.db.session.commit()

        application.db.session.rollback()