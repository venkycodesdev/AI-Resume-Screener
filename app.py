import os
import re

import pdfplumber
from docx import Document
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Skills detected by the application
SKILLS = [
    "Python",
    "Java",
    "C",
    "C++",
    "C#",
    "JavaScript",
    "TypeScript",
    "HTML",
    "CSS",
    "React",
    "Angular",
    "Vue.js",
    "Node.js",
    "Express.js",
    "Flask",
    "Django",
    "FastAPI",
    "MongoDB",
    "MySQL",
    "PostgreSQL",
    "SQLite",
    "SQL",
    "Git",
    "GitHub",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "Google Cloud",
    "Linux",
    "REST API",
    "Machine Learning",
    "Deep Learning",
    "Artificial Intelligence",
    "Natural Language Processing",
    "NLP",
    "Computer Vision",
    "TensorFlow",
    "PyTorch",
    "Keras",
    "scikit-learn",
    "Pandas",
    "NumPy",
    "OpenCV",
    "Data Structures",
    "Algorithms",
    "DSA",
    "OOP",
    "Object-Oriented Programming",
    "Communication",
    "Problem Solving",
    "Teamwork"
]


# Skill groups used for category-wise analysis
SKILL_CATEGORIES = {
    "Programming Languages": [
        "Python",
        "Java",
        "C",
        "C++",
        "C#",
        "JavaScript",
        "TypeScript"
    ],

    "Web Development": [
        "HTML",
        "CSS",
        "React",
        "Angular",
        "Vue.js",
        "Node.js",
        "Express.js",
        "Flask",
        "Django",
        "FastAPI",
        "REST API"
    ],

    "Databases": [
        "MongoDB",
        "MySQL",
        "PostgreSQL",
        "SQLite",
        "SQL"
    ],

    "Cloud and DevOps": [
        "Git",
        "GitHub",
        "Docker",
        "Kubernetes",
        "AWS",
        "Azure",
        "Google Cloud",
        "Linux"
    ],

    "AI and Machine Learning": [
        "Machine Learning",
        "Deep Learning",
        "Artificial Intelligence",
        "Natural Language Processing",
        "NLP",
        "Computer Vision",
        "TensorFlow",
        "PyTorch",
        "Keras",
        "scikit-learn",
        "Pandas",
        "NumPy",
        "OpenCV"
    ],

    "Core Computer Science": [
        "Data Structures",
        "Algorithms",
        "DSA",
        "OOP",
        "Object-Oriented Programming"
    ],

    "Soft Skills": [
        "Communication",
        "Problem Solving",
        "Teamwork"
    ]
}


CATEGORY_ICONS = {
    "Programming Languages": "💻",
    "Web Development": "🌐",
    "Databases": "🗄️",
    "Cloud and DevOps": "☁️",
    "AI and Machine Learning": "🤖",
    "Core Computer Science": "🧠",
    "Soft Skills": "🤝"
}


def allowed_file(filename):
    """
    Check whether the uploaded file has an allowed extension.
    """

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def extract_text_from_pdf(file_path):
    """
    Extract text from every readable page in a PDF file.
    """

    extracted_text = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()

            if page_text:
                extracted_text.append(page_text)

    return "\n".join(extracted_text)


def extract_text_from_docx(file_path):
    """
    Extract text from every non-empty paragraph in a DOCX file.
    """

    document = Document(file_path)
    extracted_text = []

    for paragraph in document.paragraphs:
        paragraph_text = paragraph.text.strip()

        if paragraph_text:
            extracted_text.append(paragraph_text)

    return "\n".join(extracted_text)


def extract_resume_text(file_path, extension):
    """
    Select the correct extraction function based on the file extension.
    """

    if extension == "pdf":
        return extract_text_from_pdf(file_path)

    if extension == "docx":
        return extract_text_from_docx(file_path)

    return ""


def skill_exists(skill, text):
    """
    Check whether a particular skill exists in the supplied text.
    """

    pattern = rf"(?<!\w){re.escape(skill)}(?!\w)"

    return re.search(
        pattern,
        text,
        flags=re.IGNORECASE
    ) is not None


def extract_skills(text):
    """
    Find all recognized skills in the supplied text.
    """

    detected_skills = []

    for skill in SKILLS:
        if skill_exists(skill, text):
            detected_skills.append(skill)

    return detected_skills


def generate_suggestions(
    missing_skills,
    resume_score,
    resume_skills
):
    """
    Generate personalized improvement suggestions.
    """

    suggestions = []

    for skill in missing_skills[:8]:
        suggestions.append(
            f"Learn or improve {skill} and add it to your resume "
            f"after completing a practical project."
        )

    if "GitHub" not in resume_skills:
        suggestions.append(
            "Create or update your GitHub profile and add your best projects."
        )

    if "Communication" not in resume_skills:
        suggestions.append(
            "Add communication and teamwork examples from projects, "
            "clubs or internships."
        )

    if "Problem Solving" not in resume_skills:
        suggestions.append(
            "Mention problem-solving examples and coding practice "
            "in your resume."
        )

    if resume_score < 40:
        suggestions.append(
            "Your current match is low. Focus on the most important "
            "missing skills before applying."
        )

    elif resume_score < 70:
        suggestions.append(
            "Your resume has a moderate match. Add two or three relevant "
            "projects using the missing technologies."
        )

    else:
        suggestions.append(
            "Your resume has a good match. Improve project descriptions "
            "and add measurable achievements."
        )

    return suggestions


def calculate_ats_rating(resume_score):
    """
    Convert the numerical resume score into an ATS rating.
    """

    if resume_score >= 85:
        return {
            "label": "Excellent Match",
            "stars": 5,
            "class_name": "rating-excellent",
            "message": (
                "Your resume is strongly aligned with the job requirements."
            )
        }

    if resume_score >= 70:
        return {
            "label": "Good Match",
            "stars": 4,
            "class_name": "rating-good",
            "message": (
                "Your resume matches most of the important job requirements."
            )
        }

    if resume_score >= 50:
        return {
            "label": "Average Match",
            "stars": 3,
            "class_name": "rating-average",
            "message": (
                "Your resume matches some requirements but still "
                "needs improvement."
            )
        }

    if resume_score >= 30:
        return {
            "label": "Poor Match",
            "stars": 2,
            "class_name": "rating-poor",
            "message": (
                "Your resume is missing several important skills "
                "for this role."
            )
        }

    return {
        "label": "Needs Improvement",
        "stars": 1,
        "class_name": "rating-low",
        "message": (
            "Your resume currently has a low match with "
            "this job description."
        )
    }


def calculate_resume_strength(
    extracted_text,
    resume_skills,
    resume_score
):
    """
    Calculate the overall completeness and strength of the resume.
    """

    text_lower = extracted_text.lower()

    strength_score = 0
    strong_areas = []
    improvement_areas = []

    has_email = re.search(
        r"[\w\.-]+@[\w\.-]+\.\w+",
        extracted_text
    )

    has_phone = re.search(
        r"(?:\+?\d[\d\s\-]{8,}\d)",
        extracted_text
    )

    if has_email and has_phone:
        strength_score += 15
        strong_areas.append(
            "Contact information is clearly included."
        )
    else:
        improvement_areas.append(
            "Add a professional email address and phone number."
        )

    if "linkedin" in text_lower or "github" in text_lower:
        strength_score += 10
        strong_areas.append(
            "Professional profile links are included."
        )
    else:
        improvement_areas.append(
            "Add LinkedIn and GitHub profile links."
        )

    if (
        "education" in text_lower
        or "b.tech" in text_lower
        or "bachelor" in text_lower
    ):
        strength_score += 10
        strong_areas.append(
            "Education details are available."
        )
    else:
        improvement_areas.append(
            "Add a clear education section."
        )

    if len(resume_skills) >= 8:
        strength_score += 20
        strong_areas.append(
            "The resume contains a good range of technical skills."
        )

    elif len(resume_skills) >= 4:
        strength_score += 12
        strong_areas.append(
            "The resume contains some relevant technical skills."
        )
        improvement_areas.append(
            "Add more role-related technical skills."
        )

    else:
        strength_score += 5
        improvement_areas.append(
            "Create a stronger technical-skills section."
        )

    if "project" in text_lower:
        strength_score += 15
        strong_areas.append(
            "Project experience is included."
        )
    else:
        improvement_areas.append(
            "Add two or three practical projects."
        )

    if (
        "experience" in text_lower
        or "internship" in text_lower
        or "intern" in text_lower
    ):
        strength_score += 10
        strong_areas.append(
            "Experience or internship information is included."
        )
    else:
        improvement_areas.append(
            "Add internship, training or practical experience."
        )

    if (
        "achievement" in text_lower
        or "certification" in text_lower
        or "certificate" in text_lower
    ):
        strength_score += 10
        strong_areas.append(
            "Achievements or certifications are included."
        )
    else:
        improvement_areas.append(
            "Add certifications, achievements or awards."
        )

    strength_score += round(resume_score * 0.10)

    strength_score = min(strength_score, 100)

    if strength_score >= 80:
        strength_label = "Excellent Resume"
        strength_class = "strength-excellent"

    elif strength_score >= 65:
        strength_label = "Strong Resume"
        strength_class = "strength-good"

    elif strength_score >= 45:
        strength_label = "Average Resume"
        strength_class = "strength-average"

    else:
        strength_label = "Needs Improvement"
        strength_class = "strength-low"

    return {
        "score": strength_score,
        "label": strength_label,
        "class_name": strength_class,
        "strong_areas": strong_areas,
        "improvement_areas": improvement_areas
    }


def calculate_skill_gap_analysis(
    resume_skills,
    job_skills
):
    """
    Calculate skill matching category by category.
    """

    resume_skill_set = set(resume_skills)
    job_skill_set = set(job_skills)

    category_results = []

    for category_name, category_skills in SKILL_CATEGORIES.items():
        category_skill_set = set(category_skills)

        required_skills = sorted(
            job_skill_set.intersection(category_skill_set)
        )

        if not required_skills:
            continue

        matched_skills = sorted(
            resume_skill_set.intersection(required_skills)
        )

        missing_skills = sorted(
            set(required_skills) - resume_skill_set
        )

        category_score = round(
            (len(matched_skills) / len(required_skills)) * 100
        )

        if category_score >= 75:
            status_label = "Strong"
            status_class = "category-strong"

        elif category_score >= 40:
            status_label = "Moderate"
            status_class = "category-moderate"

        else:
            status_label = "Needs Improvement"
            status_class = "category-low"

        category_results.append({
            "name": category_name,
            "icon": CATEGORY_ICONS.get(category_name, "📌"),
            "score": category_score,
            "status_label": status_label,
            "status_class": status_class,
            "required_skills": required_skills,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills
        })

    return category_results


def generate_final_recommendation(
    resume_score,
    matching_skills,
    missing_skills
):
    """
    Generate a final summary and recommended next action.
    """

    priority_skills = missing_skills[:5]

    possible_improvement = min(
        len(priority_skills) * 5,
        25
    )

    estimated_score = min(
        resume_score + possible_improvement,
        100
    )

    if resume_score >= 85:
        title = "Ready to Apply"
        class_name = "recommendation-excellent"
        message = (
            "Your resume strongly matches this job. You can apply now, "
            "but review the job description once more before submitting."
        )
        next_action = (
            "Focus on interview preparation and clearly explain your "
            "projects, skills and achievements."
        )

    elif resume_score >= 70:
        title = "Good Application Potential"
        class_name = "recommendation-good"
        message = (
            "Your resume matches most important requirements. A few focused "
            "improvements can make your application stronger."
        )
        next_action = (
            "Improve the most important missing skills and add evidence "
            "through projects, internships or certifications."
        )

    elif resume_score >= 50:
        title = "Improve Before Applying"
        class_name = "recommendation-average"
        message = (
            "Your resume has a moderate match. You may apply, but improving "
            "the missing skills will increase your selection chances."
        )
        next_action = (
            "Complete one or two practical projects using the priority "
            "skills and update your resume descriptions."
        )

    elif resume_score >= 30:
        title = "Significant Improvement Needed"
        class_name = "recommendation-poor"
        message = (
            "Your resume currently misses several important requirements "
            "from this job description."
        )
        next_action = (
            "Focus on the priority missing skills before applying. Build "
            "small projects and add the learned technologies to your resume."
        )

    else:
        title = "Build More Job-Relevant Skills"
        class_name = "recommendation-low"
        message = (
            "Your current resume has a low match for this role. Applying "
            "immediately may not give the best result."
        )
        next_action = (
            "Choose the most important missing skills, learn them in order "
            "and complete relevant projects before applying."
        )

    strongest_match = matching_skills[:5]

    return {
        "title": title,
        "class_name": class_name,
        "message": message,
        "next_action": next_action,
        "priority_skills": priority_skills,
        "strongest_match": strongest_match,
        "estimated_score": estimated_score
    }


@app.route("/")
def home():
    """
    Display the AI Resume Screener homepage.
    """

    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_resume():
    """
    Receive, temporarily save, analyze and delete an uploaded resume.
    """

    if "resume" not in request.files:
        return render_template(
            "index.html",
            upload_error="No resume file was received."
        )

    file = request.files["resume"]

    job_description = request.form.get(
        "job_description",
        ""
    ).strip()

    if file.filename == "":
        return render_template(
            "index.html",
            upload_error="Please select a resume file."
        )

    if not job_description:
        return render_template(
            "index.html",
            upload_error="Please paste the job description."
        )

    if not allowed_file(file.filename):
        return render_template(
            "index.html",
            upload_error="Only PDF and DOCX files are allowed."
        )

    filename = secure_filename(file.filename)

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    file.save(file_path)

    extension = filename.rsplit(".", 1)[1].lower()

    try:
        extracted_text = extract_resume_text(
            file_path,
            extension
        )

    except Exception as error:
        app.logger.exception(
            "Resume text extraction failed: %s",
            error
        )

        return render_template(
            "index.html",
            upload_error=(
                "The resume was uploaded, but its text "
                "could not be extracted."
            )
        )

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    if not extracted_text.strip():
        return render_template(
            "index.html",
            upload_error=(
                "The resume was uploaded, but no readable "
                "text was found."
            )
        )

    resume_skills = extract_skills(extracted_text)
    job_skills = extract_skills(job_description)

    resume_skill_set = set(resume_skills)
    job_skill_set = set(job_skills)

    matching_skills = sorted(
        resume_skill_set.intersection(job_skill_set)
    )

    missing_skills = sorted(
        job_skill_set - resume_skill_set
    )

    if job_skill_set:
        resume_score = round(
            (len(matching_skills) / len(job_skill_set)) * 100
        )
    else:
        resume_score = 0

    suggestions = generate_suggestions(
        missing_skills,
        resume_score,
        resume_skills
    )

    ats_rating = calculate_ats_rating(
        resume_score
    )

    resume_strength = calculate_resume_strength(
        extracted_text,
        resume_skills,
        resume_score
    )

    skill_gap_analysis = calculate_skill_gap_analysis(
        resume_skills,
        job_skills
    )

    final_recommendation = generate_final_recommendation(
        resume_score,
        matching_skills,
        missing_skills
    )

    return render_template(
        "index.html",
        upload_success=True,
        uploaded_filename=filename,
        extracted_text=extracted_text,
        job_description=job_description,
        resume_skills=resume_skills,
        job_skills=job_skills,
        matching_skills=matching_skills,
        missing_skills=missing_skills,
        resume_score=resume_score,
        suggestions=suggestions,
        ats_rating=ats_rating,
        resume_strength=resume_strength,
        skill_gap_analysis=skill_gap_analysis,
        final_recommendation=final_recommendation
    )


if __name__ == "__main__":
    app.run(debug=True)