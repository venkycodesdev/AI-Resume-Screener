import secrets

from flask import (
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user

from permissions import roles_required


EMPLOYMENT_TYPES = {
    "full_time": "Full-time",
    "part_time": "Part-time",
    "internship": "Internship",
    "contract": "Contract",
}


def register_job_routes(app, db, JobPosting):
    def form_token():
        if not session.get("job_csrf_token"):
            session["job_csrf_token"] = secrets.token_hex(32)
        return session["job_csrf_token"]

    def token_is_valid():
        expected = session.get("job_csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        return bool(expected) and secrets.compare_digest(
            expected.encode("utf-8"),
            submitted.encode("utf-8"),
        )

    def invalid_token_response():
        return (
            "Invalid form token. Reload the jobs page and try again.",
            400,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    def owned_job(job_id):
        return JobPosting.query.filter_by(
            id=job_id,
            recruiter_id=current_user.id,
        ).first()

    def missing_job_response():
        return (
            "Job not found.",
            404,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    def form_values(job=None):
        return {
            "title": job.title if job else "",
            "company": job.company if job else "",
            "location": job.location if job else "",
            "description": job.description if job else "",
            "employment_type": (
                job.employment_type if job else "full_time"
            ),
        }

    def validate_form(values):
        errors = []

        for field in ("title", "company", "location"):
            if not values[field]:
                errors.append(f"{field.capitalize()} is required.")
            elif len(values[field]) > 150:
                errors.append(
                    f"{field.capitalize()} must be 150 characters or fewer."
                )

        if not values["description"]:
            errors.append("Job description is required.")
        elif len(values["description"]) > 20000:
            errors.append(
                "Job description must be 20,000 characters or fewer."
            )

        if values["employment_type"] not in EMPLOYMENT_TYPES:
            errors.append("Choose a valid employment type.")

        return errors

    def render_jobs(values, errors, editing_job=None):
        jobs = JobPosting.query.filter_by(
            recruiter_id=current_user.id
        ).order_by(
            JobPosting.created_at.desc(),
            JobPosting.id.desc(),
        ).all()

        return render_template(
            "recruiter_jobs.html",
            jobs=jobs,
            values=values,
            errors=errors,
            employment_types=EMPLOYMENT_TYPES,
            csrf_token=form_token(),
            editing_job=editing_job,
        ), 400 if errors else 200

    @app.route("/recruiter/jobs", methods=["GET", "POST"])
    @roles_required("recruiter")
    def recruiter_jobs():
        values = form_values()
        errors = []

        if request.method == "POST":
            if not token_is_valid():
                return invalid_token_response()

            values = {
                field: request.form.get(field, "").strip()
                for field in values
            }
            errors = validate_form(values)

            if not errors:
                job = JobPosting(
                    recruiter_id=current_user.id,
                    status="draft",
                    **values,
                )
                db.session.add(job)
                db.session.commit()

                flash("Job draft created successfully.", "success")
                return redirect(url_for("recruiter_jobs"))

        return render_jobs(values, errors)

    @app.route(
        "/recruiter/jobs/<int:job_id>/edit",
        methods=["GET", "POST"],
    )
    @roles_required("recruiter")
    def edit_recruiter_job(job_id):
        job = owned_job(job_id)
        if job is None:
            return missing_job_response()

        values = form_values(job)
        errors = []

        if request.method == "POST":
            if not token_is_valid():
                return invalid_token_response()

            values = {
                field: request.form.get(field, "").strip()
                for field in values
            }
            errors = validate_form(values)

            if not errors:
                for field, value in values.items():
                    setattr(job, field, value)

                db.session.commit()
                flash("Job updated successfully.", "success")
                return redirect(url_for("recruiter_jobs"))

        return render_jobs(values, errors, editing_job=job)

    @app.route(
        "/recruiter/jobs/<int:job_id>/status",
        methods=["POST"],
    )
    @roles_required("recruiter")
    def change_recruiter_job_status(job_id):
        job = owned_job(job_id)
        if job is None:
            return missing_job_response()

        if not token_is_valid():
            return invalid_token_response()

        new_status = request.form.get("status", "")
        if new_status not in {"open", "closed"}:
            return (
                "Invalid job status.",
                400,
                {"Content-Type": "text/plain; charset=utf-8"},
            )

        job.status = new_status
        db.session.commit()

        flash(f"Job marked as {new_status}.", "success")
        return redirect(url_for("recruiter_jobs"))