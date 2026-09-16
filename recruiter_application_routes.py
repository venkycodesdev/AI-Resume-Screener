from datetime import datetime, timezone
from io import BytesIO
import secrets

from flask import (
    flash, redirect, render_template, request, send_file, session, url_for,
)
from flask_login import current_user
from sqlalchemy.orm import defer
from werkzeug.utils import secure_filename

from permissions import roles_required


STATUS_TRANSITIONS = {
    "submitted": ("under_review", "shortlisted", "rejected"),
    "under_review": ("shortlisted", "rejected"),
    "shortlisted": ("under_review", "hired", "rejected"),
    "rejected": (),
    "hired": (),
    "withdrawn": (),
}

STATUS_LABELS = {
    "submitted": "Submitted",
    "under_review": "Under review",
    "shortlisted": "Shortlisted",
    "rejected": "Rejected",
    "hired": "Hired",
    "withdrawn": "Withdrawn",
}


def register_recruiter_application_routes(
    app, JobPosting, JobApplication, User, db, Notification,
):
    def owned_job(job_id):
        return JobPosting.query.filter_by(
            id=job_id, recruiter_id=current_user.id,
        ).first()

    def error_response(message, status):
        return message, status, {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "private, no-store",
        }

    def not_found():
        return error_response("Job or application not found.", 404)

    def status_csrf_token():
        token = session.get("application_status_csrf_token")
        if not token:
            token = secrets.token_hex(32)
            session["application_status_csrf_token"] = token
        return token

    def valid_status_csrf():
        expected = session.get("application_status_csrf_token")
        supplied = request.form.get("csrf_token", "")
        return (
            isinstance(expected, str)
            and bool(expected)
            and secrets.compare_digest(
                expected.encode("utf-8"), supplied.encode("utf-8")
            )
        )

    @app.route("/recruiter/jobs/<int:job_id>/applicants")
    @roles_required("recruiter")
    def recruiter_job_applicants(job_id):
        job = owned_job(job_id)
        if job is None:
            return not_found()
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            return error_response("Invalid page number.", 400)
        if page < 1:
            return error_response("Invalid page number.", 400)

        pagination = (
            JobApplication.query.options(
                defer(JobApplication.resume_content),
                defer(JobApplication.resume_text),
                defer(JobApplication.job_description_snapshot),
            )
            .filter_by(job_id=job.id)
            .order_by(
                JobApplication.submitted_at.desc(), JobApplication.id.desc()
            )
            .paginate(page=page, per_page=10, error_out=False)
        )
        candidate_ids = {
            submission.candidate_id for submission in pagination.items
        }
        names = {}
        if candidate_ids:
            names = dict(User.query.with_entities(
                User.id, User.name
            ).filter(User.id.in_(candidate_ids)).all())

        response = app.make_response(render_template(
            "recruiter_applicants.html",
            job=job,
            pagination=pagination,
            candidate_names=names,
            status_transitions=STATUS_TRANSITIONS,
            status_labels=STATUS_LABELS,
            status_csrf_token=status_csrf_token(),
        ))
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.route(
        "/recruiter/jobs/<int:job_id>/applications/"
        "<int:application_id>/status", methods=["POST"],
    )
    @roles_required("recruiter")
    def update_applicant_status(job_id, application_id):
        job = owned_job(job_id)
        if job is None:
            return not_found()
        submission = JobApplication.query.options(
            defer(JobApplication.resume_content),
            defer(JobApplication.resume_text),
            defer(JobApplication.job_description_snapshot),
        ).filter_by(id=application_id, job_id=job.id).first()
        if submission is None:
            return not_found()
        if not valid_status_csrf():
            return error_response(
                "Invalid security token. Reload the applicants page "
                "and try again.", 400,
            )
        try:
            page = int(request.form.get("page", "1"))
        except ValueError:
            return error_response("Invalid page number.", 400)
        if page < 1:
            return error_response("Invalid page number.", 400)

        expected_status = request.form.get("expected_status", "")
        new_status = request.form.get("status", "")
        if expected_status not in STATUS_TRANSITIONS:
            return error_response("Invalid current status.", 400)
        if new_status not in STATUS_LABELS:
            return error_response("Invalid application status.", 400)
        if submission.status != expected_status:
            return error_response(
                "This application changed since you opened the page. "
                "Reload the applicants page before updating it.", 409,
            )
        if new_status not in STATUS_TRANSITIONS[expected_status]:
            return error_response("This status change is not allowed.", 400)

        owned_job_ids = db.session.query(JobPosting.id).filter(
            JobPosting.id == job_id,
            JobPosting.recruiter_id == current_user.id,
        )
        try:
            changed = JobApplication.query.filter(
                JobApplication.id == application_id,
                JobApplication.job_id.in_(owned_job_ids),
                JobApplication.status == expected_status,
            ).update(
                {
                    JobApplication.status: new_status,
                    JobApplication.updated_at: datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
            if changed != 1:
                db.session.rollback()
                return error_response(
                    "This application changed or is no longer available. "
                    "Reload the applicants page before updating it.", 409,
                )

            db.session.add(Notification(
                user_id=submission.candidate_id,
                kind="application_status",
                title="Application status updated",
                message=(
                    f"Your application #{application_id} for "
                    f"{submission.job_title_snapshot} is now "
                    f"{STATUS_LABELS[new_status]}."
                ),
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        flash(
            f"Application #{application_id} marked "
            f"{STATUS_LABELS[new_status]}.", "success",
        )
        return redirect(url_for(
            "recruiter_job_applicants", job_id=job_id, page=page
        ))

    @app.route(
        "/recruiter/jobs/<int:job_id>/applications/"
        "<int:application_id>/resume"
    )
    @roles_required("recruiter")
    def download_applicant_resume(job_id, application_id):
        job = owned_job(job_id)
        if job is None:
            return not_found()
        submission = JobApplication.query.filter_by(
            id=application_id, job_id=job.id
        ).first()
        if submission is None:
            return not_found()

        filename = secure_filename(submission.resume_filename)
        extension = filename.rsplit(".", 1)[-1].lower()
        mime_types = {
            "pdf": "application/pdf",
            "docx": (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        }
        if extension not in mime_types:
            return error_response("This resume format is unavailable.", 400)

        response = send_file(
            BytesIO(submission.resume_content),
            mimetype=mime_types[extension],
            as_attachment=True,
            download_name=filename,
            conditional=False,
            etag=False,
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
