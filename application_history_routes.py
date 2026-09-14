from flask import render_template, request
from flask_login import current_user
from sqlalchemy.orm import defer

from permissions import roles_required


APPLICATION_STATUSES = {
    "submitted": "Submitted",
    "under_review": "Under review",
    "shortlisted": "Shortlisted",
    "rejected": "Rejected",
    "hired": "Hired",
    "withdrawn": "Withdrawn",
}


def register_application_history_routes(app, JobApplication):
    @app.route("/candidate/applications")
    @roles_required("candidate")
    def candidate_applications():
        selected_status = request.args.get("status", "").strip()

        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            return "Invalid page number.", 400

        if page < 1:
            return "Invalid page number.", 400

        if selected_status and selected_status not in APPLICATION_STATUSES:
            return "Invalid application status.", 400

        # Load only the candidate's records.
        # Large resume fields are unnecessary for this list.
        query = JobApplication.query.options(
            defer(JobApplication.resume_content),
            defer(JobApplication.resume_text),
            defer(JobApplication.job_description_snapshot),
        ).filter_by(candidate_id=current_user.id)

        if selected_status:
            query = query.filter_by(status=selected_status)

        pagination = query.order_by(
            JobApplication.submitted_at.desc(),
            JobApplication.id.desc(),
        ).paginate(
            page=page,
            per_page=10,
            error_out=False,
        )

        return render_template(
            "candidate_applications.html",
            pagination=pagination,
            selected_status=selected_status,
            statuses=APPLICATION_STATUSES,
        )