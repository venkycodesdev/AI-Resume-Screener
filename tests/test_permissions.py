import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

from permissions import roles_required


class TestAccount(UserMixin):
    # Prevent pytest from collecting this helper as a test class.
    __test__ = False

    def __init__(self, role):
        self.id = role
        self.role = role


@pytest.fixture
def permission_client():
    # This separate test app does not use your project database.
    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=True,
        SECRET_KEY="permissions-test-secret",
    )

    login_manager = LoginManager(test_app)
    login_manager.login_view = "login"

    accounts = {
        role: TestAccount(role)
        for role in ("candidate", "recruiter", "admin")
    }

    @login_manager.user_loader
    def load_user(user_id):
        return accounts.get(user_id)

    @test_app.get("/login")
    def login():
        return "Login"

    @test_app.get("/candidate")
    @roles_required("candidate")
    def candidate_page():
        return "Candidate page"

    @test_app.get("/recruiter")
    @roles_required("recruiter")
    def recruiter_page():
        return "Recruiter page"

    @test_app.get("/admin")
    @roles_required("admin")
    def admin_page():
        return "Admin page"

    return test_app.test_client()


@pytest.mark.parametrize(
    "signed_in_role",
    [None, "candidate", "recruiter", "admin"],
)
@pytest.mark.parametrize(
    "page_role",
    ["candidate", "recruiter", "admin"],
)
def test_role_access(permission_client, signed_in_role, page_role):
    if signed_in_role is not None:
        with permission_client.session_transaction() as session:
            session["_user_id"] = signed_in_role
            session["_fresh"] = True

    response = permission_client.get(f"/{page_role}")

    if signed_in_role is None:
        assert response.status_code == 302
        assert "/login?" in response.headers["Location"]
    elif signed_in_role == page_role:
        assert response.status_code == 200
        assert response.get_data(as_text=True) == (
            f"{page_role.capitalize()} page"
        )
    else:
        assert response.status_code == 403


@pytest.mark.parametrize(
    "roles",
    [(), ("superuser",), ("admin", "recrutier")],
)
def test_invalid_role_configuration_is_rejected(roles):
    with pytest.raises(ValueError):
        roles_required(*roles)