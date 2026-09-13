from functools import wraps

from flask import abort
from flask_login import current_user, login_required


VALID_ROLES = frozenset({"candidate", "recruiter", "admin"})


def roles_required(*allowed_roles):
    """Require login and one of the explicitly allowed roles."""
    if not allowed_roles or not set(allowed_roles).issubset(VALID_ROLES):
        raise ValueError("Provide valid roles: candidate, recruiter or admin.")

    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if getattr(current_user, "role", None) not in allowed_roles:
                abort(403)

            return view(*args, **kwargs)

        return login_required(wrapped_view)

    return decorator