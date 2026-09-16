import secrets
from datetime import datetime, timezone

from flask import redirect, render_template, request, session, url_for
from flask_login import current_user

from permissions import roles_required


def register_notification_routes(app, db, Notification):
    def error_response(message, status):
        return message, status, {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "private, no-store",
        }

    def csrf_token():
        token = session.get("notification_csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["notification_csrf_token"] = token
        return token

    def valid_csrf():
        expected = session.get("notification_csrf_token")
        supplied = request.form.get("csrf_token", "")
        return (
            isinstance(expected, str)
            and bool(expected)
            and secrets.compare_digest(
                expected.encode("utf-8"), supplied.encode("utf-8")
            )
        )

    def parse_page(value):
        try:
            page = int(value)
        except (TypeError, ValueError):
            return None
        return page if page >= 1 else None

    @app.route("/notifications")
    @roles_required("candidate", "recruiter", "admin")
    def notifications():
        page = parse_page(request.args.get("page", "1"))
        if page is None:
            return error_response("Invalid page number.", 400)

        owned = Notification.query.filter_by(user_id=current_user.id)
        pagination = owned.order_by(
            Notification.created_at.desc(), Notification.id.desc()
        ).paginate(page=page, per_page=10, error_out=False)
        unread_count = owned.filter(Notification.read_at.is_(None)).count()

        response = app.make_response(render_template(
            "notifications.html",
            pagination=pagination,
            unread_count=unread_count,
            csrf_token=csrf_token(),
        ))
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.route("/notifications/<int:notification_id>/read", methods=["POST"])
    @roles_required("candidate", "recruiter", "admin")
    def mark_notification_read(notification_id):
        if not valid_csrf():
            return error_response(
                "Invalid security token. Reload the page and try again.", 400
            )
        page = parse_page(request.form.get("page", "1"))
        if page is None:
            return error_response("Invalid page number.", 400)

        notification = Notification.query.filter_by(
            id=notification_id, user_id=current_user.id
        ).first()
        if notification is None:
            return error_response("Notification not found.", 404)

        try:
            Notification.query.filter(
                Notification.id == notification_id,
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None),
            ).update(
                {Notification.read_at: datetime.now(timezone.utc)},
                synchronize_session=False,
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return redirect(url_for("notifications", page=page))
