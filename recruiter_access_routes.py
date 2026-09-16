import secrets
from datetime import datetime, timezone
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


def register_recruiter_access_routes(
    app,
    db,
    User,
    RecruiterAccessRequest,
):
    def error_response(message, status):
        return (
            message,
            status,
            {
                "Content-Type": "text/plain; charset=utf-8",
                "Cache-Control": "private, no-store",
            },
        )

    def csrf_token():
        token = session.get("recruiter_access_csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["recruiter_access_csrf_token"] = token
        return token

    def valid_csrf():
        expected = session.get("recruiter_access_csrf_token")
        supplied = request.form.get("csrf_token", "")
        return (
            isinstance(expected, str)
            and bool(expected)
            and secrets.compare_digest(
                expected.encode("utf-8"),
                supplied.encode("utf-8"),
            )
        )

    def page_response(template, status=200, **context):
        response = app.make_response(
            (
                render_template(
                    template,
                    csrf_token=csrf_token(),
                    **context,
                ),
                status,
            )
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def valid_website(value):
        if not value:
            return True

        if (
            len(value) > 500
            or "\\" in value
            or any(
                character.isspace() or ord(character) < 32
                for character in value
            )
        ):
            return False

        try:
            parsed = urlsplit(value)
            return (
                parsed.scheme.lower() == "https"
                and bool(parsed.hostname)
                and "." in parsed.hostname
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
            )
        except ValueError:
            return False

    @app.route("/candidate/recruiter-access", methods=["GET", "POST"])
    @roles_required("candidate")
    def candidate_recruiter_access():
        existing = RecruiterAccessRequest.query.filter_by(
            user_id=current_user.id,
        ).first()

        values = {
            "company_name": "",
            "company_website": "",
            "reason": "",
        }

        if request.method == "GET":
            return page_response(
                "recruiter_access.html",
                submission=existing,
                values=values,
                errors=[],
            )

        if not valid_csrf():
            return error_response(
                "Invalid security token. Reload the page and try again.",
                400,
            )

        if existing is not None:
            return error_response(
                "You already have a recruiter-access request. "
                "Reload the page to see its status.",
                409,
            )

        values = {
            key: request.form.get(key, "").strip()
            for key in values
        }
        errors = []

        if not 1 <= len(values["company_name"]) <= 150:
            errors.append("Company name must contain 1–150 characters.")

        if not 20 <= len(values["reason"]) <= 2000:
            errors.append(
                "Explain your hiring needs using 20–2000 characters."
            )

        if any("\x00" in value for value in values.values()):
            errors.append("Your request contains an invalid character.")

        if not valid_website(values["company_website"]):
            errors.append(
                "Company website must be a valid HTTPS URL of "
                "500 characters or fewer, or left blank."
            )

        if errors:
            return page_response(
                "recruiter_access.html",
                status=400,
                submission=None,
                values=values,
                errors=errors,
            )

        submission = RecruiterAccessRequest(
            user_id=current_user.id,
            company_name=values["company_name"],
            company_website=values["company_website"],
            reason=values["reason"],
            status="pending",
        )

        try:
            db.session.add(submission)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return error_response(
                "Your request could not be saved because of a "
                "conflicting submission. Reload the page.",
                409,
            )
        except Exception:
            db.session.rollback()
            raise

        flash("Your recruiter-access request has been submitted.", "success")
        return redirect(url_for("candidate_recruiter_access"))

    @app.route("/admin/recruiter-requests")
    @roles_required("admin")
    def admin_recruiter_requests():
        selected_status = request.args.get("status", "pending")
        if selected_status not in {
            "pending", "approved", "rejected", "all"
        }:
            return error_response("Invalid request status.", 400)

        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            return error_response("Invalid page number.", 400)

        if page < 1:
            return error_response("Invalid page number.", 400)

        query = RecruiterAccessRequest.query
        if selected_status != "all":
            query = query.filter_by(status=selected_status)

        pagination = query.order_by(
            RecruiterAccessRequest.submitted_at.asc(),
            RecruiterAccessRequest.id.asc(),
        ).paginate(page=page, per_page=10, error_out=False)

        user_ids = {item.user_id for item in pagination.items}
        user_ids.update(
            item.reviewed_by_id
            for item in pagination.items
            if item.reviewed_by_id is not None
        )

        users = {}
        if user_ids:
            users = {
                user.id: user
                for user in User.query.filter(User.id.in_(user_ids)).all()
            }

        return page_response(
            "admin_recruiter_requests.html",
            pagination=pagination,
            users=users,
            selected_status=selected_status,
        )

    @app.route(
        "/admin/recruiter-requests/<int:request_id>/review",
        methods=["POST"],
    )
    @roles_required("admin")
    def review_recruiter_request(request_id):
        if not valid_csrf():
            return error_response(
                "Invalid security token. Reload the page and try again.",
                400,
            )

        decision = request.form.get("decision", "")
        note = request.form.get("review_note", "").strip()

        if decision not in {"approved", "rejected"}:
            return error_response("Invalid review decision.", 400)

        if len(note) > 2000 or "\x00" in note:
            return error_response(
                "Review note must be 2000 characters or fewer "
                "and contain no null characters.",
                400,
            )

        if decision == "rejected" and not note:
            return error_response(
                "Please give the applicant a reason for rejection.",
                400,
            )

        submission = db.session.get(RecruiterAccessRequest, request_id)
        if submission is None:
            return error_response("Request not found.", 404)

        if submission.user_id == current_user.id:
            return error_response("You cannot review your own request.", 403)

        applicant_id = submission.user_id

        try:
            # Lock the applicant first so role changes are coordinated.
            applicant = (
                User.query.filter_by(id=applicant_id)
                .populate_existing()
                .with_for_update()
                .first()
            )

            if applicant is None or applicant.role != "candidate":
                db.session.rollback()
                return error_response(
                    "The applicant is no longer a candidate. "
                    "Reload the review page.",
                    409,
                )

            # Only a pending request can be reviewed.
            changed = RecruiterAccessRequest.query.filter_by(
                id=request_id,
                status="pending",
            ).update(
                {
                    RecruiterAccessRequest.status: decision,
                    RecruiterAccessRequest.reviewed_by_id: current_user.id,
                    RecruiterAccessRequest.reviewed_at: datetime.now(
                        timezone.utc
                    ),
                    RecruiterAccessRequest.review_note: note,
                },
                synchronize_session=False,
            )

            if changed != 1:
                db.session.rollback()
                return error_response(
                    "This request has already been reviewed. "
                    "Reload the review page.",
                    409,
                )

            if decision == "approved":
                role_changed = User.query.filter_by(
                    id=applicant_id,
                    role="candidate",
                ).update(
                    {User.role: "recruiter"},
                    synchronize_session=False,
                )

                if role_changed != 1:
                    db.session.rollback()
                    return error_response(
                        "The applicant's role changed. Reload the page.",
                        409,
                    )

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        flash(f"Request #{request_id} {decision}.", "success")
        return redirect(url_for("admin_recruiter_requests"))