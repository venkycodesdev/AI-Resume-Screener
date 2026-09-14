import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import (
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from permissions import roles_required


def register_application_routes(
    app,
    db,
    JobPosting,
    JobApplication,
    validate_uploaded_file,
    extract_resume_text,
):
    def csrf_token():
        if not session.get("application_csrf_token"):
            session["application_csrf_token"] = secrets.token_hex(32)
        return session["application_csrf_token"]

    def valid_token():
        expected = session.get("application_csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        return bool(expected) and secrets.compare_digest(
            expected.encode("utf-8"),
            submitted.encode("utf-8"),
        )

    def plain_error(message, status):
        return (
            message,
            status,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    def existing_application(job_id):
        return JobApplication.query.filter_by(
            candidate_id=current_user.id,
            job_id=job_id,
        ).first()

    def confirmation_redirect(application):
        return redirect(
            url_for(
                "application_confirmation",
                application_id=application.id,
            )
        )

    @app.route(
        "/candidate/jobs/<int:job_id>/apply",
        methods=["GET", "POST"],
    )
    @roles_required("candidate")
    def apply_to_job(job_id):
        if request.method == "POST" and not valid_token():
            return plain_error(
                "Invalid form token. Reload the application page.",
                400,
            )

        previous = existing_application(job_id)
        if previous is not None:
            return confirmation_redirect(previous)

        job = JobPosting.query.filter_by(
            id=job_id,
            status="open",
        ).first()

        if job is None:
            return plain_error("This job is unavailable.", 404)

        error = None

        if request.method == "POST":
            uploaded = request.files.get("resume")
            filename, extension, size, error = validate_uploaded_file(
                uploaded,
                file_label="resume",
            )

            if not error and len(filename) > 255:
                error = "Please shorten your resume filename."

            content = None
            resume_text = ""

            if not error:
                uploaded.stream.seek(0)
                content = uploaded.stream.read(10 * 1024 * 1024 + 1)

                if len(content) > 10 * 1024 * 1024:
                    error = "Your resume must be 10 MB or smaller."
                elif not content:
                    error = "Your resume file is empty."

            if not error:
                try:
                    with TemporaryDirectory() as directory:
                        path = Path(directory) / f"resume.{extension}"
                        path.write_bytes(content)
                        resume_text = extract_resume_text(
                            str(path),
                            extension,
                        ).strip()
                except Exception:
                    app.logger.warning(
                        "Resume parsing failed for an application."
                    )
                    error = (
                        "We could not read this resume. "
                        "Upload a valid, unencrypted PDF or DOCX."
                    )

                if not error and not resume_text:
                    error = (
                        "No readable text was found. "
                        "Upload a text-based PDF or DOCX resume."
                    )

                if not error and len(resume_text) > 200000:
                    error = "The resume contains too much text."

            if not error:
                # Recheck the job after reading the upload.
                job = (
                    JobPosting.query.filter_by(id=job_id)
                    .populate_existing()
                    .with_for_update()
                    .first()
                )

                if job is None or job.status != "open":
                    db.session.rollback()
                    return plain_error("This job is unavailable.", 404)

                application = JobApplication(
                    candidate_id=current_user.id,
                    job_id=job.id,
                    resume_filename=filename,
                    resume_content=content,
                    resume_text=resume_text,
                    job_title_snapshot=job.title,
                    job_description_snapshot=job.description,
                    status="submitted",
                )

                db.session.add(application)

                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    previous = existing_application(job_id)
                    if previous is not None:
                        return confirmation_redirect(previous)
                    raise

                return confirmation_redirect(application)

        return render_template(
            "job_application.html",
            job=job,
            application=None,
            error=error,
            csrf_token=csrf_token(),
        ), 400 if error else 200

    @app.route("/candidate/applications/<int:application_id>")
    @roles_required("candidate")
    def application_confirmation(application_id):
        application = JobApplication.query.filter_by(
            id=application_id,
            candidate_id=current_user.id,
        ).first()

        if application is None:
            return plain_error("Application not found.", 404)

        return render_template(
            "job_application.html",
            job=None,
            application=application,
            error=None,
        )