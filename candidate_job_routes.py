from flask import render_template, request
from sqlalchemy import or_

from job_routes import EMPLOYMENT_TYPES
from permissions import roles_required


def register_candidate_job_routes(app, JobPosting):
    @app.route("/candidate/jobs")
    @roles_required("candidate")
    def candidate_jobs():
        search = request.args.get("q", "").strip()
        employment_type = request.args.get("employment_type", "").strip()

        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            return "Invalid page number.", 400

        if page < 1:
            return "Invalid page number.", 400

        if len(search) > 150:
            return "Search must be 150 characters or fewer.", 400

        if employment_type and employment_type not in EMPLOYMENT_TYPES:
            return "Invalid employment type.", 400

        query = JobPosting.query.filter_by(status="open")

        if search:
            # Treat SQL wildcard characters as literal search text.
            escaped = (
                search.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"

            query = query.filter(
                or_(
                    JobPosting.title.ilike(pattern, escape="\\"),
                    JobPosting.company.ilike(pattern, escape="\\"),
                    JobPosting.location.ilike(pattern, escape="\\"),
                )
            )

        if employment_type:
            query = query.filter_by(employment_type=employment_type)

        pagination = query.order_by(
            JobPosting.created_at.desc(),
            JobPosting.id.desc(),
        ).paginate(
            page=page,
            per_page=12,
            error_out=False,
        )

        return render_template(
            "candidate_jobs.html",
            job=None,
            pagination=pagination,
            search=search,
            selected_type=employment_type,
            employment_types=EMPLOYMENT_TYPES,
        )

    @app.route("/candidate/jobs/<int:job_id>")
    @roles_required("candidate")
    def candidate_job_detail(job_id):
        job = JobPosting.query.filter_by(
            id=job_id,
            status="open",
        ).first()

        if job is None:
            return (
                "This job is unavailable.",
                404,
                {"Content-Type": "text/plain; charset=utf-8"},
            )

        return render_template(
            "candidate_jobs.html",
            job=job,
            employment_types=EMPLOYMENT_TYPES,
        )