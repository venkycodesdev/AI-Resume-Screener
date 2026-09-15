import secrets
from urllib.parse import urlsplit

from flask import (
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from permissions import roles_required


PROFILE_FIELDS = (
    ("headline", "Headline", 150, "text"),
    ("bio", "Short bio", 2000, "textarea"),
    ("location", "Location", 150, "text"),
    ("skills", "Skills", 2000, "textarea"),
    ("education", "Education", 255, "text"),
    ("github_url", "GitHub URL", 500, "url"),
    ("linkedin_url", "LinkedIn URL", 500, "url"),
    ("portfolio_url", "Portfolio URL", 500, "url"),
)

URL_HOSTS = {
    "github_url": {"github.com", "www.github.com"},
    "linkedin_url": {"linkedin.com", "www.linkedin.com"},
}


def validate_profile(values):
    errors = {}

    for key, label, limit, field_type in PROFILE_FIELDS:
        value = values[key]

        if len(value) > limit:
            errors[key] = f"{label} must be {limit} characters or fewer."
            continue

        if "\x00" in value:
            errors[key] = f"{label} contains an invalid character."
            continue

        if field_type != "url" or not value:
            continue

        if any(character.isspace() for character in value):
            errors[key] = "URLs cannot contain whitespace."
            continue

        if "\\" in value or any(ord(character) < 32 for character in value):
            errors[key] = "Enter a valid HTTPS URL."
            continue

        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            port = parsed.port

            if (
                parsed.scheme.lower() != "https"
                or not hostname
                or "." not in hostname
                or parsed.username is not None
                or parsed.password is not None
                or port not in (None, 443)
            ):
                errors[key] = "Enter a complete HTTPS URL."
                continue

            allowed_hosts = URL_HOSTS.get(key)
            if allowed_hosts and hostname.lower() not in allowed_hosts:
                errors[key] = (
                    "Use a github.com URL."
                    if key == "github_url"
                    else "Use a linkedin.com URL."
                )
        except ValueError:
            errors[key] = "Enter a valid HTTPS URL."

    year_text = values["graduation_year"]
    year = None

    if year_text:
        if (
            len(year_text) != 4
            or not year_text.isascii()
            or not year_text.isdigit()
        ):
            errors["graduation_year"] = (
                "Enter a four-digit year between 1900 and 2100."
            )
        else:
            year = int(year_text)
            if not 1900 <= year <= 2100:
                errors["graduation_year"] = (
                    "Graduation year must be between 1900 and 2100."
                )

    return errors, year


def register_candidate_profile_routes(app, db, CandidateProfile):
    def csrf_token():
        token = session.get("candidate_profile_csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["candidate_profile_csrf_token"] = token
        return token

    def valid_csrf():
        expected = session.get("candidate_profile_csrf_token")
        supplied = request.form.get("csrf_token", "")

        return (
            isinstance(expected, str)
            and bool(expected)
            and secrets.compare_digest(
                expected.encode("utf-8"),
                supplied.encode("utf-8"),
            )
        )

    def render_profile(values, errors=None, status=200):
        response = app.make_response(
            (
                render_template(
                    "candidate_profile.html",
                    values=values,
                    errors=errors or {},
                    profile_fields=PROFILE_FIELDS,
                    csrf_token=csrf_token(),
                ),
                status,
            )
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.route("/candidate/profile", methods=["GET", "POST"])
    @roles_required("candidate")
    def candidate_profile():
        profile = CandidateProfile.query.filter_by(
            user_id=current_user.id,
        ).first()

        if request.method == "GET":
            values = {
                key: getattr(profile, key, "") or ""
                for key, _, _, _ in PROFILE_FIELDS
            }
            values["graduation_year"] = (
                str(profile.graduation_year)
                if profile and profile.graduation_year is not None
                else ""
            )
            return render_profile(values)

        values = {
            key: request.form.get(key, "").strip()
            for key, _, _, _ in PROFILE_FIELDS
        }
        values["graduation_year"] = request.form.get(
            "graduation_year", ""
        ).strip()

        if not valid_csrf():
            return render_profile(
                values,
                {
                    "form": (
                        "Your security token is invalid or expired. "
                        "Reload this page and try again."
                    )
                },
                400,
            )

        errors, graduation_year = validate_profile(values)
        if errors:
            return render_profile(values, errors, 400)

        try:
            if profile is None:
                profile = CandidateProfile(user_id=current_user.id)
                db.session.add(profile)

            # Only these profile fields may be changed.
            for key, _, _, _ in PROFILE_FIELDS:
                setattr(profile, key, values[key])

            profile.graduation_year = graduation_year
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return render_profile(
                values,
                {
                    "form": (
                        "Your profile could not be saved because of "
                        "a conflicting update. Reload the page and retry."
                    )
                },
                409,
            )
        except Exception:
            db.session.rollback()
            raise

        flash("Your profile has been saved.", "success")
        return redirect(url_for("candidate_profile"))