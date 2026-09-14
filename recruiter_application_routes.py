from io import BytesIO

from flask import render_template, request, send_file
from flask_login import current_user
from sqlalchemy.orm import defer
from werkzeug.utils import secure_filename

from permissions import roles_required


def register_recruiter_application_routes(
    app,
    JobPosting,
    JobApplication,
    User,
):
    def owned_job(job_id):
        return JobPosting.query.filter_by(
            id=job_id,
            recruiter_id=current_user.id,
        ).first()

    def not_found():
        return (
            "Job or application not found.",
            404,
            {"Content-Type": "text/plain; charset=utf-8"},
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
            return "Invalid page number.", 400

        if page < 1:
            return "Invalid page number.", 400

        pagination = (
            JobApplication.query.options(
                defer(JobApplication.resume_content),
                defer(JobApplication.resume_text),
                defer(JobApplication.job_description_snapshot),
            )
            .filter_by(job_id=job.id)
            .order_by(
                JobApplication.submitted_at.desc(),
                JobApplication.id.desc(),
            )
            .paginate(
                page=page,
                per_page=10,
                error_out=False,
            )
        )

        candidate_ids = {
            submission.candidate_id
            for submission in pagination.items
        }

        names = {}
        if candidate_ids:
            names = dict(
                User.query.with_entities(
                    User.id,
                    User.name,
                ).filter(User.id.in_(candidate_ids)).all()
            )

        response = app.make_response(
            render_template(
                "recruiter_applicants.html",
                job=job,
                pagination=pagination,
                candidate_names=names,
            )
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response

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
            id=application_id,
            job_id=job.id,
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
            return (
                "This resume format is unavailable.",
                400,
                {"Content-Type": "text/plain; charset=utf-8"},
            )

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