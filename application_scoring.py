import math


APPLICATION_WEIGHTS = {
    "skills": 40,
    "experience": 30,
    "projects": 20,
    "education": 10,
}

SCORING_VERSION = "application-scoring-1"


def build_application_score(
    resume_text,
    job_description,
    extract_skills,
    calculate_score_breakdown,
    scoring_api,
):
    if not resume_text or not resume_text.strip():
        raise ValueError("The application has no readable resume text.")

    if not job_description or not job_description.strip():
        raise ValueError("The application has no job description.")

    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)

    matching = sorted(set(resume_skills) & set(job_skills))
    missing = sorted(set(job_skills) - set(resume_skills))

    breakdown = calculate_score_breakdown(
        resume_text,
        job_description,
        matching,
        job_skills,
    )

    weights = APPLICATION_WEIGHTS.copy()

    overall_score = float(
        scoring_api.weighted_score(breakdown, weights)
    )

    if not math.isfinite(overall_score):
        raise ValueError("Scoring returned a non-finite result.")

    if not 0 <= overall_score <= 100:
        raise ValueError("Scoring returned a result outside 0–100.")

    explanations = scoring_api.build_explanations(
        resume_text,
        job_description,
        breakdown,
        matching,
        missing,
    )

    return {
        "overall_score": overall_score,
        "score_breakdown": breakdown,
        "weights": weights,
        "matching_skills": matching,
        "missing_skills": missing,
        "explanations": explanations,
        "scoring_version": SCORING_VERSION,
    }