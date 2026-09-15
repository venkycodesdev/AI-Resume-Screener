import secrets
from datetime import datetime, timezone

from flask import (
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy.orm import defer

from application_scoring import build_application_score
from permissions import roles_required


def register_application_score_routes(
    app,
    db,
    JobPosting,
    JobApplication,
    ApplicationScore,
    User,
    extract_skills,
    calculate_score_breakdown,
    scoring_api,
):
    def error_response(message, status):
        return (
            message,
            status,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    def csrf_token():
        if not session.get("scoring_csrf_token"):
            session["scoring_csrf_token"] = secrets.token_hex(32)
        return session["scoring_csrf_token"]

    def valid_token():
        expected = session.get("scoring_csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        return bool(expected) and secrets.compare_digest(
            expected.encode("utf-8"),
            submitted.encode("utf-8"),
        )

    @app.route(
        "/recruiter/jobs/<int:job_id>/scores",
        methods=["GET", "POST"],
    )
    @roles_required("recruiter")
    def recruiter_application_scores(job_id):
        job = JobPosting.query.filter_by(
            id=job_id,
            recruiter_id=current_user.id,
        ).first()

        if job is None:
            return error_response("Job not found.", 404)

        if request.method == "POST":
            if not valid_token():
                return error_response(
                    "Invalid form token. Reload the scores page.",
                    400,
                )

            # Serialize scoring requests for this job on PostgreSQL.
            job = (
                JobPosting.query.filter_by(
                    id=job_id,
                    recruiter_id=current_user.id,
                )
                .populate_existing()
                .with_for_update()
                .first()
            )

            if job is None:
                db.session.rollback()
                return error_response("Job not found.", 404)

            submissions = (
                JobApplication.query.options(
                    defer(JobApplication.resume_content)
                )
                .filter_by(job_id=job.id)
                .order_by(JobApplication.id)
                .all()
            )

            if not submissions:
                db.session.rollback()
                flash("There are no applications to score.")
                return redirect(
                    url_for("recruiter_application_scores", job_id=job_id)
                )

            application_ids = [item.id for item in submissions]
            existing_scores = {
                score.application_id: score
                for score in ApplicationScore.query.filter(
                    ApplicationScore.application_id.in_(application_ids)
                ).all()
            }

            scored_at = datetime.now(timezone.utc)

            try:
                for submission in submissions:
                    result = build_application_score(
                        resume_text=submission.resume_text,
                        job_description=(
                            submission.job_description_snapshot
                        ),
                        extract_skills=extract_skills,
                        calculate_score_breakdown=calculate_score_breakdown,
                        scoring_api=scoring_api,
                    )

                    score = existing_scores.get(submission.id)
                    if score is None:
                        score = ApplicationScore(
                            application_id=submission.id,
                        )
                        db.session.add(score)

                    for field, value in result.items():
                        setattr(score, field, value)

                    score.scored_by_id = current_user.id
                    score.scored_at = scored_at

                db.session.commit()

            except (ValueError, TypeError, KeyError):
                db.session.rollback()
                app.logger.warning(
                    "Application scoring could not finish for job %s.",
                    job_id,
                )
                return error_response(
                    "Scoring could not finish. No score changes were saved.",
                    400,
                )

            except Exception:
                db.session.rollback()
                raise

            flash(f"Scores saved for {len(submissions)} application(s).")
            return redirect(
                url_for("recruiter_application_scores", job_id=job_id)
            )

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
            )
            .outerjoin(
                ApplicationScore,
                ApplicationScore.application_id == JobApplication.id,
            )
            .filter(JobApplication.job_id == job.id)
            .order_by(
                ApplicationScore.overall_score.is_(None),
                ApplicationScore.overall_score.desc(),
                JobApplication.submitted_at.asc(),
                JobApplication.id.asc(),
            )
            .paginate(page=page, per_page=10, error_out=False)
        )

        application_ids = [item.id for item in pagination.items]
        candidate_ids = {
            item.candidate_id for item in pagination.items
        }

        scores = {}
        names = {}

        if application_ids:
            scores = {
                score.application_id: score
                for score in ApplicationScore.query.filter(
                    ApplicationScore.application_id.in_(application_ids)
                ).all()
            }

        if candidate_ids:
            names = dict(
                User.query.with_entities(User.id, User.name)
                .filter(User.id.in_(candidate_ids))
                .all()
            )

        descriptions = (
            JobApplication.query.with_entities(
                JobApplication.job_description_snapshot
            )
            .filter_by(job_id=job.id)
            .distinct()
            .limit(2)
            .all()
        )

        response = app.make_response(
            render_template(
                "application_scores.html",
                job=job,
                pagination=pagination,
                scores=scores,
                candidate_names=names,
                csrf_token=csrf_token(),
                mixed_descriptions=len(descriptions) > 1,
            )
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response