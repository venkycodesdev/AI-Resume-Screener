import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

import pdfplumber
from docx import Document
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)
from werkzeug.utils import secure_filename


app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "development-secret-key-change-later",
)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    db_path = os.path.join(INSTANCE_DIR, "users.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


class User(UserMixin, db.Model):
    """
    Store registered user account information.
    """

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(100),
        nullable=False,
    )

    email = db.Column(
        db.String(150),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def set_password(self, password):
        """
        Convert a plain-text password into a secure password hash.
        """

        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """
        Compare a plain-text password with the stored password hash.
        """

        return check_password_hash(
            self.password_hash,
            password,
        )


class Analysis(db.Model):
    """Store resume analysis history for each logged-in user."""

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    resume_filename = db.Column(
        db.String(255),
        nullable=False,
    )

    analysis_type = db.Column(
        db.String(50),
        nullable=False,
        default="single",
    )

    job_description = db.Column(
        db.Text,
        nullable=False,
    )

    match_score = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    detected_skills = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )

    matching_skills = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )

    missing_skills = db.Column(
        db.Text,
        nullable=False,
        default="[]",
    )

    candidate_rank = db.Column(
        db.Integer,
        nullable=True,
    )

    # STEP 18.7 - Saved interview questions
    interview_questions = db.Column(
        db.Text,
        nullable=False,
        default="{}",
    )
    
    # STEP 19.6 - Save score breakdown in history
    score_breakdown = db.Column(
        db.Text,
        nullable=False,
        default="{}",
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "analyses",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )


@login_manager.user_loader
def load_user(user_id):
    """
    Load the currently logged-in user from the database.
    """

    try:
        return db.session.get(
            User,
            int(user_id),
        )

    except (TypeError, ValueError):
        return None


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
    "Teamwork",
]


# Skill categories used for category-wise analysis
SKILL_CATEGORIES = {
    "Programming Languages": [
        "Python",
        "Java",
        "C",
        "C++",
        "C#",
        "JavaScript",
        "TypeScript",
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
        "REST API",
    ],

    "Databases": [
        "MongoDB",
        "MySQL",
        "PostgreSQL",
        "SQLite",
        "SQL",
    ],

    "Cloud and DevOps": [
        "Git",
        "GitHub",
        "Docker",
        "Kubernetes",
        "AWS",
        "Azure",
        "Google Cloud",
        "Linux",
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
        "OpenCV",
    ],

    "Core Computer Science": [
        "Data Structures",
        "Algorithms",
        "DSA",
        "OOP",
        "Object-Oriented Programming",
    ],

    "Soft Skills": [
        "Communication",
        "Problem Solving",
        "Teamwork",
    ],
}


CATEGORY_ICONS = {
    "Programming Languages": "💻",
    "Web Development": "🌐",
    "Databases": "🗄️",
    "Cloud and DevOps": "☁️",
    "AI and Machine Learning": "🤖",
    "Core Computer Science": "🧠",
    "Soft Skills": "🤝",
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
    Extract text from every readable PDF page.
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
    Extract text from every non-empty DOCX paragraph.
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
    Select the correct text extractor.
    """

    if extension == "pdf":
        return extract_text_from_pdf(file_path)

    if extension == "docx":
        return extract_text_from_docx(file_path)

    return ""


def skill_exists(skill, text):
    """
    Check whether one skill exists in the supplied text.
    """

    pattern = rf"(?<!\w){re.escape(skill)}(?!\w)"

    return re.search(
        pattern,
        text,
        flags=re.IGNORECASE,
    ) is not None


def extract_skills(text):
    """
    Detect recognized skills in the supplied text.
    """

    detected_skills = []

    for skill in SKILLS:
        if skill_exists(skill, text):
            detected_skills.append(skill)

    return detected_skills


def validate_detected_job_skills(job_skills):
    """Return True when at least one recognized job skill was detected."""
    return bool(job_skills)


def highlight_keywords(text, skills):
    """Escape text and wrap recognized skills in safe mark tags."""
    if not text:
        return ""
    highlighted_text = escape(text)
    for skill in sorted(skills or [], key=len, reverse=True):
        pattern = re.compile(
            rf"(?<!\w){re.escape(skill)}(?!\w)",
            re.IGNORECASE,
        )
        highlighted_text = pattern.sub(
            lambda m: f'<mark class="keyword-highlight">{m.group(0)}</mark>',
            highlighted_text,
        )
    return highlighted_text


def generate_suggestions(
    missing_skills,
    resume_score,
    resume_skills,
):
    """
    Generate personalized resume suggestions.
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
    Convert the score into an ATS rating.
    """

    if resume_score >= 85:
        return {
            "label": "Excellent Match",
            "stars": 5,
            "class_name": "rating-excellent",
            "message": (
                "Your resume is strongly aligned with the job requirements."
            ),
        }

    if resume_score >= 70:
        return {
            "label": "Good Match",
            "stars": 4,
            "class_name": "rating-good",
            "message": (
                "Your resume matches most of the important job requirements."
            ),
        }

    if resume_score >= 50:
        return {
            "label": "Average Match",
            "stars": 3,
            "class_name": "rating-average",
            "message": (
                "Your resume matches some requirements but still "
                "needs improvement."
            ),
        }

    if resume_score >= 30:
        return {
            "label": "Poor Match",
            "stars": 2,
            "class_name": "rating-poor",
            "message": (
                "Your resume is missing several important skills "
                "for this role."
            ),
        }

    return {
        "label": "Needs Improvement",
        "stars": 1,
        "class_name": "rating-low",
        "message": (
            "Your resume currently has a low match with this job description."
        ),
    }


def calculate_resume_strength(
    extracted_text,
    resume_skills,
    resume_score,
):
    """
    Calculate resume completeness and strength.
    """

    text_lower = extracted_text.lower()

    strength_score = 0
    strong_areas = []
    improvement_areas = []

    has_email = re.search(
        r"[\w\.-]+@[\w\.-]+\.\w+",
        extracted_text,
    )

    has_phone = re.search(
        r"(?:\+?\d[\d\s\-]{8,}\d)",
        extracted_text,
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
        "improvement_areas": improvement_areas,
    }


# ==========================================
# STEP 19.2 - RESUME SCORE BREAKDOWN
# ==========================================

def calculate_score_breakdown(
    resume_text,
    job_description,
    matching_skills,
    job_skills,
):
    """
    Calculate separate scores for:
    1. Skills Match
    2. Experience Relevance
    3. Education Match
    4. Projects Relevance
    """

    resume_lower = (resume_text or "").lower()
    job_lower = (job_description or "").lower()

    # --------------------------------------
    # 1. SKILLS MATCH SCORE
    # --------------------------------------

    if job_skills:
        skills_score = round(
            len(matching_skills) / len(job_skills) * 100
        )
    else:
        skills_score = 0

    skills_score = max(0, min(100, skills_score))

    # --------------------------------------
    # 2. EXPERIENCE RELEVANCE SCORE
    # --------------------------------------

    experience_keywords = [
        "experience",
        "internship",
        "intern",
        "worked",
        "developed",
        "implemented",
        "built",
        "designed",
        "deployed",
        "professional",
    ]

    resume_experience_count = sum(
        1
        for keyword in experience_keywords
        if keyword in resume_lower
    )

    job_experience_count = sum(
        1
        for keyword in experience_keywords
        if keyword in job_lower
    )

    if job_experience_count > 0:
        experience_score = round(
            min(
                resume_experience_count /
                job_experience_count,
                1,
            ) * 100
        )
    else:
        experience_score = min(
            resume_experience_count * 20,
            100,
        )

# --------------------------------------
    # 3. EDUCATION MATCH SCORE
    # --------------------------------------

    education_keywords = [
        "b.tech",
        "btech",
        "bachelor",
        "degree",
        "engineering",
        "computer science",
        "artificial intelligence",
        "machine learning",
        "m.tech",
        "master",
    ]

    required_education = [
        keyword
        for keyword in education_keywords
        if keyword in job_lower
    ]

    resume_education = [
        keyword
        for keyword in education_keywords
        if keyword in resume_lower
    ]

    if required_education:

        matched_education = [
            keyword
            for keyword in required_education
            if keyword in resume_lower
        ]

        education_score = round(
            len(matched_education) /
            len(required_education) *
            100
        )

    elif resume_education:

        education_score = 100

    else:

        education_score = 0

    # --------------------------------------
    # 4. PROJECTS RELEVANCE SCORE
    # --------------------------------------

    project_keywords = [
        "project",
        "projects",
        "developed",
        "built",
        "created",
        "implemented",
        "application",
        "system",
        "website",
        "model",
    ]

    resume_project_count = sum(
        1
        for keyword in project_keywords
        if keyword in resume_lower
    )

    job_project_count = sum(
        1
        for keyword in project_keywords
        if keyword in job_lower
    )

    if job_project_count > 0:

        projects_score = round(
            min(
                resume_project_count /
                job_project_count,
                1,
            ) * 100
        )

    else:

        projects_score = min(
            resume_project_count * 15,
            100,
        )

# --------------------------------------
# FINAL BREAKDOWN
# --------------------------------------

    return {
        "skills": max(0, min(100, skills_score)),
        "experience": max(0, min(100, experience_score)),
        "education": max(0, min(100, education_score)),
        "projects": max(0, min(100, projects_score)),
    }


# ==================================================
# STEP 19.5 - TARGETED IMPROVEMENT RECOMMENDATIONS
# ==================================================

def generate_targeted_recommendations(
    score_breakdown,
    missing_skills,
):
    """
    Generate focused improvement recommendations
    using the four resume score categories.
    """

    recommendations = []

    skills_score = score_breakdown.get("skills", 0)
    experience_score = score_breakdown.get("experience", 0)
    education_score = score_breakdown.get("education", 0)
    projects_score = score_breakdown.get("projects", 0)

    # 1. SKILLS
    if skills_score < 60:
        if missing_skills:
            priority_skills = ", ".join(missing_skills[:5])
            skills_message = (
                "Your skills match needs improvement. "
                f"Focus on learning or demonstrating: {priority_skills}."
            )
        else:
            skills_message = (
                "Strengthen the technical skills section and clearly "
                "mention job-relevant tools and technologies."
            )

    elif skills_score < 80:
        skills_message = (
            "Your skills match is good, but you can improve it by "
            "adding evidence of the remaining job-relevant skills."
        )

    else:
        skills_message = (
            "Your technical skills are strongly aligned with the job "
            "requirements. Keep them clearly visible in your resume."
        )

    recommendations.append({
        "category": "Skills",
        "icon": "💻",
        "score": skills_score,
        "message": skills_message,
    })

    # 2. EXPERIENCE
    if experience_score < 50:
        experience_message = (
            "Add stronger experience evidence through internships, "
            "practical work, freelancing, leadership activities or "
            "relevant project responsibilities."
        )

    elif experience_score < 80:
        experience_message = (
            "Improve your experience section by describing your "
            "responsibilities, technologies used and measurable results."
        )

    else:
        experience_message = (
            "Your experience section shows good relevance. Keep "
            "achievements specific and quantify results where possible."
        )

    recommendations.append({
        "category": "Experience",
        "icon": "💼",
        "score": experience_score,
        "message": experience_message,
    })

    # 3. EDUCATION
    if education_score < 50:
        education_message = (
            "Make your education details clearer. Mention your degree, "
            "specialization, institution and relevant coursework."
        )

    elif education_score < 80:
        education_message = (
            "Your education is partly aligned. Highlight relevant "
            "coursework, certifications or academic work."
        )

    else:
        education_message = (
            "Your education information is well aligned. Keep the most "
            "job-relevant academic details easy to identify."
        )

    recommendations.append({
        "category": "Education",
        "icon": "🎓",
        "score": education_score,
        "message": education_message,
    })

    # 4. PROJECTS
    if projects_score < 50:
        projects_message = (
            "Add more relevant projects that demonstrate the skills "
            "required for this role. Mention the problem, technologies "
            "and outcome."
        )

    elif projects_score < 80:
        projects_message = (
            "Your projects provide useful evidence, but they can be "
            "stronger. Add measurable outcomes and explain your "
            "individual contribution."
        )

    else:
        projects_message = (
            "Your projects show strong relevance. Keep the most "
            "important projects prominent and include technologies, "
            "responsibilities and results."
        )

    recommendations.append({
        "category": "Projects",
        "icon": "🚀",
        "score": projects_score,
        "message": projects_message,
    })

    return recommendations


def calculate_skill_gap_analysis(
    resume_skills,
    job_skills,
):
    """
    Calculate category-wise skill gaps.
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

        category_results.append(
            {
                "name": category_name,
                "icon": CATEGORY_ICONS.get(category_name, "📌"),
                "score": category_score,
                "status_label": status_label,
                "status_class": status_class,
                "required_skills": required_skills,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
            }
        )

    return category_results


def generate_final_recommendation(
    resume_score,
    matching_skills,
    missing_skills,
):
    """
    Generate the final recommendation.
    """

    priority_skills = missing_skills[:5]

    possible_improvement = min(
        len(priority_skills) * 5,
        25,
    )

    estimated_score = min(
        resume_score + possible_improvement,
        100,
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
        "estimated_score": estimated_score,
    }
    
    # --------------------------------------------------
# STEP 18.3 - INTERVIEW QUESTION GENERATOR
# --------------------------------------------------


def generate_interview_questions(
    resume_skills,
    matching_skills,
    missing_skills,
):
    """
    Generate interview questions based on:
    - skills detected in the resume
    - matching job skills
    - missing job skills
    """

    technical_questions = []
    resume_questions = []
    job_questions = []

    # --------------------------------------------------
    # TECHNICAL QUESTIONS
    # --------------------------------------------------

    for skill in matching_skills[:5]:

        technical_questions.append(
            f"Explain your practical experience with {skill}."
        )

        technical_questions.append(
            f"What important concepts should a developer know in {skill}?"
        )

    # --------------------------------------------------
    # RESUME-BASED QUESTIONS
    # --------------------------------------------------

    for skill in resume_skills[:5]:

        resume_questions.append(
            f"Describe a project where you used {skill}."
        )

    resume_questions.extend(
        [
            "What was the most challenging problem you solved in a project?",
            "Which project on your resume are you most confident explaining?",
            "How do you test and debug your applications?",
        ]
    )

    # --------------------------------------------------
    # JOB-FOCUSED QUESTIONS
    # --------------------------------------------------

    for skill in missing_skills[:5]:

        job_questions.append(
            f"This role requires {skill}. "
            f"What do you currently know about it?"
        )

        job_questions.append(
            f"How would you improve your knowledge of {skill} "
            f"if you were selected for this role?"
        )

    # --------------------------------------------------
    # FALLBACK QUESTIONS
    # --------------------------------------------------

    if not technical_questions:
        technical_questions = [
            "Explain the strongest technical skill listed on your resume.",
            "How do you approach solving a new programming problem?",
        ]

    if not resume_questions:
        resume_questions = [
            "Tell me about one technical project you have completed.",
            "What was your contribution to that project?",
        ]

    if not job_questions:
        job_questions = [
            "Why are you interested in this role?",
            "Which of your skills are most relevant to this position?",
        ]

    return {
        "technical_questions": technical_questions[:10],
        "resume_questions": resume_questions[:8],
        "job_questions": job_questions[:10],
    }


def safe_json_list(value):
    """
    Convert a JSON form value into a Python list.
    """

    if not value:
        return []

    try:
        parsed_value = json.loads(value)

        if isinstance(parsed_value, list):
            return [
                str(item)
                for item in parsed_value
            ]

    except (json.JSONDecodeError, TypeError):
        return []

    return []


def create_skill_text(skills):
    """
    Convert a skills list into safe text for the PDF.
    """

    if not skills:
        return "None detected"

    return ", ".join(
        escape(str(skill))
        for skill in skills
    )


def add_report_page_number(canvas, document):
    """
    Add footer text and page numbers.
    """

    canvas.saveState()

    page_width, _ = A4

    canvas.setStrokeColor(
        colors.HexColor("#CBD5E1")
    )

    canvas.line(
        18 * mm,
        15 * mm,
        page_width - 18 * mm,
        15 * mm,
    )

    canvas.setFont(
        "Helvetica",
        8,
    )

    canvas.setFillColor(
        colors.HexColor("#64748B")
    )

    canvas.drawString(
        18 * mm,
        9 * mm,
        "AI Resume Screener Analysis Report",
    )

    canvas.drawRightString(
        page_width - 18 * mm,
        9 * mm,
        f"Page {document.page}",
    )

    canvas.restoreState()


def build_analysis_pdf(report_data):
    """
    Create the analysis PDF in memory.
    """

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title="AI Resume Screener Analysis Report",
        author="AI Resume Screener",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_CENTER,
        spaceAfter=18,
    )

    section_style = ParagraphStyle(
        "ReportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0369A1"),
        spaceBefore=14,
        spaceAfter=9,
    )

    normal_style = ParagraphStyle(
        "ReportNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )

    recommendation_style = ParagraphStyle(
        "Recommendation",
        parent=normal_style,
        leftIndent=8,
        borderColor=colors.HexColor("#A78BFA"),
        borderWidth=1,
        borderPadding=8,
        backColor=colors.HexColor("#F5F3FF"),
        spaceAfter=8,
    )

    story = []

    story.append(
        Paragraph(
            "AI Resume Screener",
            title_style,
        )
    )

    story.append(
        Paragraph(
            "Professional Resume Analysis Report",
            subtitle_style,
        )
    )

    overview_data = [
        [
            Paragraph(
                "<b>Uploaded Resume</b>",
                normal_style,
            ),
            Paragraph(
                escape(report_data["filename"]),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>File Type</b>",
                normal_style,
            ),
            Paragraph(
                escape(report_data["file_type"]),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>File Size</b>",
                normal_style,
            ),
            Paragraph(
                escape(report_data["file_size"]),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>Extracted Words</b>",
                normal_style,
            ),
            Paragraph(
                str(report_data["word_count"]),
                normal_style,
            ),
        ],
    ]

    overview_table = Table(
        overview_data,
        colWidths=[
            52 * mm,
            105 * mm,
        ],
    )

    overview_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#E0F2FE"),
                ),
                (
                    "BACKGROUND",
                    (1, 0),
                    (1, -1),
                    colors.HexColor("#F8FAFC"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#CBD5E1"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
            ]
        )
    )

    story.append(overview_table)
    story.append(Spacer(1, 12))

    score_data = [
        [
            Paragraph(
                "<b>Match Score</b>",
                normal_style,
            ),
            Paragraph(
                "<b>ATS Rating</b>",
                normal_style,
            ),
            Paragraph(
                "<b>Resume Strength</b>",
                normal_style,
            ),
        ],
        [
            Paragraph(
                f"<b>{report_data['resume_score']}%</b>",
                normal_style,
            ),
            Paragraph(
                escape(report_data["ats_label"]),
                normal_style,
            ),
            Paragraph(
                (
                    f"{escape(report_data['strength_label'])} "
                    f"({report_data['strength_score']}%)"
                ),
                normal_style,
            ),
        ],
    ]

    score_table = Table(
        score_data,
        colWidths=[
            52 * mm,
            52 * mm,
            53 * mm,
        ],
    )

    score_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#0F172A"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "BACKGROUND",
                    (0, 1),
                    (-1, 1),
                    colors.HexColor("#F8FAFC"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#CBD5E1"),
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
            ]
        )
    )

    story.append(score_table)
    
    # --------------------------------------------------
    # STEP 19.7 - SCORE BREAKDOWN IN PDF
    # --------------------------------------------------

    story.append(
        Paragraph(
            "Detailed Resume Performance",
            section_style,
        )
    )

    score_breakdown_data = [
        [
            Paragraph(
                "<b>Category</b>",
                normal_style,
            ),
            Paragraph(
                "<b>Score</b>",
                normal_style,
            ),
        ],
        [
            Paragraph(
                "Skills Match",
                normal_style,
            ),
            Paragraph(
                f"{report_data['skills_score']}%",
                normal_style,
            ),
        ],
        [
            Paragraph(
                "Experience Relevance",
                normal_style,
            ),
            Paragraph(
                f"{report_data['experience_score']}%",
                normal_style,
            ),
        ],
        [
            Paragraph(
                "Education Match",
                normal_style,
            ),
            Paragraph(
                f"{report_data['education_score']}%",
                normal_style,
            ),
        ],
        [
            Paragraph(
                "Projects Relevance",
                normal_style,
            ),
            Paragraph(
                f"{report_data['projects_score']}%",
                normal_style,
            ),
        ],
    ]

    score_breakdown_table = Table(
        score_breakdown_data,
        colWidths=[
            105 * mm,
            52 * mm,
        ],
    )

    score_breakdown_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#E0F2FE"),
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.HexColor("#CBD5E1"),
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
        ])
    )

    story.append(score_breakdown_table)
    story.append(Spacer(1, 12))

    story.append(
        Paragraph(
            "Matching Skills",
            section_style,
        )
    )

    story.append(
        Paragraph(
            create_skill_text(
                report_data["matching_skills"]
            ),
            normal_style,
        )
    )

    story.append(
        Paragraph(
            "Missing Skills",
            section_style,
        )
    )

    story.append(
        Paragraph(
            create_skill_text(
                report_data["missing_skills"]
            ),
            normal_style,
        )
    )

    story.append(
        Paragraph(
            "Strong Areas",
            section_style,
        )
    )

    if report_data["strong_areas"]:
        for area in report_data["strong_areas"]:
            story.append(
                Paragraph(
                    f"- {escape(area)}",
                    normal_style,
                )
            )
    else:
        story.append(
            Paragraph(
                "No strong areas were detected.",
                normal_style,
            )
        )

    story.append(
        Paragraph(
            "Areas That Need Improvement",
            section_style,
        )
    )

    if report_data["improvement_areas"]:
        for area in report_data["improvement_areas"]:
            story.append(
                Paragraph(
                    f"- {escape(area)}",
                    normal_style,
                )
            )
    else:
        story.append(
            Paragraph(
                "No major improvement areas were detected.",
                normal_style,
            )
        )

    story.append(PageBreak())

    story.append(
        Paragraph(
            "AI Resume Recommendations",
            section_style,
        )
    )

    if report_data["suggestions"]:
        for suggestion in report_data["suggestions"]:
            story.append(
                Paragraph(
                    escape(suggestion),
                    recommendation_style,
                )
            )
    else:
        story.append(
            Paragraph(
                "No additional recommendations were generated.",
                normal_style,
            )
        )

    story.append(
        Paragraph(
            "Final Recommendation",
            section_style,
        )
    )
    
    story.append(
        Paragraph(
            f"<b>{escape(report_data['final_title'])}</b>",
            normal_style,
        )
    )

    story.append(
        Paragraph(
            escape(report_data["final_message"]),
            normal_style,
        )
    )

    story.append(
        Paragraph(
            "<b>Recommended next action:</b>",
            normal_style,
        )
    )

    story.append(
        Paragraph(
            escape(report_data["next_action"]),
            recommendation_style,
        )
    )

    # --------------------------------------------------
    # STEP 18.8 - INTERVIEW QUESTIONS IN PDF
    # --------------------------------------------------

    story.append(
        Paragraph(
            "AI-Generated Interview Questions",
            section_style,
        )
    )

    story.append(
        Paragraph(
            "<b>Technical Questions</b>",
            normal_style,
        )
    )

    if report_data["technical_questions"]:
        for number, question in enumerate(
            report_data["technical_questions"],
            start=1,
        ):
            story.append(
                Paragraph(
                    f"{number}. {escape(question)}",
                    normal_style,
                )
            )
    else:
        story.append(
            Paragraph(
                "No technical questions were generated.",
                normal_style,
            )
        )

    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "<b>Resume-Based Questions</b>",
            normal_style,
        )
    )

    if report_data["resume_questions"]:
        for number, question in enumerate(
            report_data["resume_questions"],
            start=1,
        ):
            story.append(
                Paragraph(
                    f"{number}. {escape(question)}",
                    normal_style,
                )
            )
    else:
        story.append(
            Paragraph(
                "No resume-based questions were generated.",
                normal_style,
            )
        )

    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "<b>Job-Focused Questions</b>",
            normal_style,
        )
    )

    if report_data["job_questions"]:
        for number, question in enumerate(
            report_data["job_questions"],
            start=1,
        ):
            story.append(
                Paragraph(
                    f"{number}. {escape(question)}",
                    normal_style,
                )
            )
    else:
        story.append(
            Paragraph(
                "No job-focused questions were generated.",
                normal_style,
            )
        )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "Important Notice",
            section_style,
        )
    )

    story.append(
        Paragraph(
            (
                "This report provides guidance based on recognized keywords, "
                "resume sections and job-description skill matching. It does "
                "not guarantee selection, interview invitations or a specific "
                "result from another Applicant Tracking System."
            ),
            normal_style,
        )
    )

    document.build(
        story,
        onFirstPage=add_report_page_number,
        onLaterPages=add_report_page_number,
    )

    pdf_buffer.seek(0)

    return pdf_buffer


@app.errorhandler(413)
def file_too_large(error):
    if request.path.startswith("/multiple-resume"):
        flash(
            "One or more uploaded files are too large. "
            "Maximum request size is 10 MB.",
            "danger",
        )
        return redirect(url_for("multiple_resume"))
    error_message = (
        "The uploaded file is too large. Maximum request size is 10 MB."
    )
    return render_template("index.html", upload_error=error_message), 413


@app.route("/")
def landing():
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        terms_accepted = request.form.get("terms")

        if not name:
            flash("Please enter your full name.", "danger")
            return redirect(url_for("register"))
        if not email:
            flash("Please enter your email address.", "danger")
            return redirect(url_for("register"))
        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return redirect(url_for("register"))
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))
        if not terms_accepted:
            flash(
                "Please accept the Terms of Use and Privacy Policy.",
                "warning",
            )
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "warning")
            return redirect(url_for("register"))

        new_user = User(name=name, email=email)
        new_user.set_password(password)
        try:
            db.session.add(new_user)
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            app.logger.exception("User registration failed: %s", error)
            flash(
                "Something went wrong while creating your account.",
                "danger",
            )
            return redirect(url_for("register"))

        flash("Account created successfully! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        if not email or not password:
            flash("Please enter your email and password.", "danger")
            return redirect(url_for("login"))
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("Invalid email or password. Please try again.", "danger")
            return redirect(url_for("login"))
        login_user(user, remember=remember)
        flash(f"Welcome back, {user.name}!", "success")
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/resume-screener")
@login_required
def home():
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


@app.route("/history")
@login_required
def history():
    analyses = Analysis.query.filter_by(
        user_id=current_user.id
    ).order_by(Analysis.created_at.desc()).all()
    for analysis in analyses:
        try:
            analysis.matching_skills_list = json.loads(
                analysis.matching_skills or "[]"
            )
        except (json.JSONDecodeError, TypeError):
            analysis.matching_skills_list = []
        try:
            analysis.missing_skills_list = json.loads(
                analysis.missing_skills or "[]"
            )
        except (json.JSONDecodeError, TypeError):
            analysis.missing_skills_list = []
    return render_template("history.html", analyses=analyses)


@app.route("/history/<int:analysis_id>")
@login_required
def analysis_details(analysis_id):
    analysis = Analysis.query.filter_by(
        id=analysis_id,
        user_id=current_user.id,
    ).first_or_404()

    try:
        matching_skills = json.loads(
            analysis.matching_skills or "[]"
        )
    except (json.JSONDecodeError, TypeError):
        matching_skills = []

    try:
        missing_skills = json.loads(
            analysis.missing_skills or "[]"
        )
    except (json.JSONDecodeError, TypeError):
        missing_skills = []

    try:
        detected_skills = json.loads(
            analysis.detected_skills or "[]"
        )
    except (json.JSONDecodeError, TypeError):
        detected_skills = []
        
    try:
        interview_questions = json.loads(
            analysis.interview_questions or "{}"
        )
    except (json.JSONDecodeError, TypeError):
        interview_questions = {}

    # STEP 19.6D - Load saved score breakdown
    try:
        score_breakdown = json.loads(
            analysis.score_breakdown or "{}"
        )
    except (json.JSONDecodeError, TypeError):
        score_breakdown = {}

    return render_template(
        "analysis_details.html",
        analysis=analysis,
        matching_skills=matching_skills,
        missing_skills=missing_skills,
        detected_skills=detected_skills,
        interview_questions=interview_questions,
        score_breakdown=score_breakdown,
    )


@app.route("/history/<int:analysis_id>/delete", methods=["POST"])
@login_required
def delete_analysis(analysis_id):
    analysis = Analysis.query.filter_by(
        id=analysis_id, user_id=current_user.id
    ).first_or_404()
    try:
        db.session.delete(analysis)
        db.session.commit()
        flash("Analysis deleted successfully.", "success")
    except Exception as error:
        db.session.rollback()
        app.logger.exception("Failed to delete analysis: %s", error)
        flash("Could not delete the analysis. Please try again.", "danger")
    return redirect(url_for("history"))


def extract_uploaded_jd(form_text, uploaded_file, prefix):
    job_description = (form_text or "").strip()
    has_uploaded = uploaded_file is not None and uploaded_file.filename != ""
    if not job_description and not has_uploaded:
        return None, (
            "Please paste the job description or upload a PDF/DOCX "
            "job description."
        )
    if has_uploaded:
        if not allowed_file(uploaded_file.filename):
            return None, "Job description file must be PDF or DOCX."
        filename = secure_filename(uploaded_file.filename)
        extension = filename.rsplit(".", 1)[1].lower()
        path = os.path.join(
            app.config["UPLOAD_FOLDER"], f"{prefix}_{filename}"
        )
        try:
            uploaded_file.save(path)
            text = extract_resume_text(path, extension).strip()
            if not text:
                return None, (
                    "No readable text was found inside the "
                    "uploaded job description file."
                )
            job_description = text
        except Exception:
            app.logger.exception(
                "Job description extraction failed"
            )
            return None, "The uploaded job description could not be processed."
        finally:
            if os.path.exists(path):
                os.remove(path)
    return job_description, None


@app.route("/multiple-resume")
@login_required
def multiple_resume():
    return render_template("multiple_resume.html")


@app.route("/multiple-resume/analyze", methods=["POST"])
@login_required
def analyze_multiple_resumes():
    job_description, error = extract_uploaded_jd(
        request.form.get("job_description", ""),
        request.files.get("job_description_file"),
        "multi_jd",
    )
    if error:
        flash(error, "danger")
        return redirect(url_for("multiple_resume"))

    job_skills = extract_skills(job_description)
    if not validate_detected_job_skills(job_skills):
        flash(
            "The job description contains no recognized skills. "
            "Please provide a more detailed job description.",
            "warning"
        )
        return redirect(url_for("multiple_resume"))
    job_skill_set = set(job_skills)

    files = request.files.getlist("resumes")
    valid_files = [file for file in files if file and file.filename]
    if len(valid_files) < 2:
        flash("Please upload at least two resumes.", "warning")
        return redirect(url_for("multiple_resume"))

    uploaded_names = [secure_filename(file.filename) for file in valid_files]
    if len(uploaded_names) != len(set(uploaded_names)):
        flash(
            "Duplicate resume filenames were detected. "
            "Please rename the files and upload them again.",
            "warning"
        )
        return redirect(url_for("multiple_resume"))

    candidates = []
    for file in valid_files:
        if not allowed_file(file.filename):
            flash(
                f"{file.filename} is not a valid PDF or DOCX file.",
                "danger"
            )
            return redirect(url_for("multiple_resume"))
        filename = secure_filename(file.filename)
        extension = filename.rsplit(".", 1)[1].lower()
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        try:
            file.save(path)
            text = extract_resume_text(path, extension).strip()
        except Exception as error:
            app.logger.exception(
                "Text extraction failed for %s: %s", filename, error
            )
            flash(f"Could not extract text from {filename}.", "danger")
            return redirect(url_for("multiple_resume"))
        finally:
            if os.path.exists(path):
                os.remove(path)
        if not text:
            flash(f"No readable text was found in {filename}.", "warning")
            return redirect(url_for("multiple_resume"))

        resume_skills = extract_skills(text)
        resume_skill_set = set(resume_skills)
        matching_skills = sorted(resume_skill_set & job_skill_set)
        missing_skills = sorted(job_skill_set - resume_skill_set)
        score = round(len(matching_skills) / len(job_skill_set) * 100)
        
                # STEP 19.8 - 4-category score breakdown
        score_breakdown = calculate_score_breakdown(
            text,
            job_description,
            matching_skills,
            job_skills,
        )
        candidates.append({
            "filename": filename,
            "file_type": extension.upper(),
            "extracted_text": text,
            "word_count": len(text.split()),
            "character_count": len(text),
            "line_count": len([
                line for line in text.splitlines() if line.strip()
            ]),
            "resume_skills": resume_skills,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "match_score": score,
            "score_breakdown": score_breakdown,
        })

    candidates.sort(key=lambda c: c["match_score"], reverse=True)
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank

    try:
        for candidate in candidates:
            db.session.add(Analysis(
                user_id=current_user.id,
                resume_filename=candidate["filename"],
                analysis_type="multiple",
                job_description=job_description,
                match_score=candidate["match_score"],
                detected_skills=json.dumps(candidate["resume_skills"]),
                matching_skills=json.dumps(candidate["matching_skills"]),
                missing_skills=json.dumps(candidate["missing_skills"]),
                candidate_rank=candidate["rank"],
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to save multiple-resume history")

    return render_template(
        "multiple_resume.html",
        extraction_success=True,
        candidates=candidates,
        uploaded_names=[c["filename"] for c in candidates],
        upload_success=True,
        job_description=job_description,
        job_skills=job_skills,
    )


@app.route("/upload", methods=["POST"])
@login_required
def upload_resume():
    if "resume" not in request.files:
        return render_template(
            "index.html", upload_error="No resume file was received."
        )
    file = request.files["resume"]
    if file.filename == "":
        return render_template(
            "index.html", upload_error="Please select a resume file."
        )
    if not allowed_file(file.filename):
        return render_template(
            "index.html",
            upload_error="Only PDF and DOCX resume files are allowed.",
        )

    job_description, error = extract_uploaded_jd(
        request.form.get("job_description", ""),
        request.files.get("job_description_file"),
        "jd",
    )
    if error:
        return render_template("index.html", upload_error=error)

    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[1].lower()
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    try:
        file.save(path)
        size = os.path.getsize(path)
        text = extract_resume_text(path, extension).strip()
    except Exception as error:
        app.logger.exception("Resume processing failed: %s", error)
        return render_template(
            "index.html",
            upload_error="The resume could not be processed.",
        )
    finally:
        if os.path.exists(path):
            os.remove(path)
    if not text:
        return render_template(
            "index.html",
            upload_error=(
                "The resume was uploaded, but no readable text was found."
            ),
        )

    if size < 1024:
        formatted_size = f"{size} bytes"
    elif size < 1024 * 1024:
        formatted_size = f"{size / 1024:.2f} KB"
    else:
        formatted_size = f"{size / (1024 * 1024):.2f} MB"

    resume_info = {
        "filename": filename,
        "file_type": extension.upper(),
        "file_size": formatted_size,
        "word_count": len(text.split()),
        "character_count": len(text),
        "line_count": len(
            [line for line in text.splitlines() if line.strip()]
        ),
        "status": "Successfully processed",
    }

    resume_skills = extract_skills(text)
    job_skills = extract_skills(job_description)
    if not validate_detected_job_skills(job_skills):
        return render_template(
            "index.html",
            upload_error=(
                "The job description contains no recognized skills. "
                "Please provide a more detailed job description."
            ),
        )

    resume_set, job_set = set(resume_skills), set(job_skills)
    matching_skills = sorted(resume_set & job_set)
    missing_skills = sorted(job_set - resume_set)
    resume_score = round(len(matching_skills) / len(job_set) * 100)
    suggestions = generate_suggestions(
        missing_skills, resume_score, resume_skills
    )
    ats_rating = calculate_ats_rating(resume_score)
    resume_strength = calculate_resume_strength(
        text, resume_skills, resume_score
    )
    skill_gap_analysis = calculate_skill_gap_analysis(
        resume_skills, job_skills
    )
    final_recommendation = generate_final_recommendation(
        resume_score,
        matching_skills,
        missing_skills,
    )

    score_breakdown = calculate_score_breakdown(
        text,
        job_description,
        matching_skills,
        job_skills,
    )
    
    targeted_recommendations = generate_targeted_recommendations(
        score_breakdown,
        missing_skills,
    )

    interview_questions = generate_interview_questions(
        resume_skills,
        matching_skills,
        missing_skills,
    )

    highlighted_resume_text = highlight_keywords(text, job_skills)
    highlighted_job_description = highlight_keywords(
        job_description, job_skills
    )

    try:
        db.session.add(Analysis(
            user_id=current_user.id,
            resume_filename=filename,
            analysis_type="single",
            job_description=job_description,
            match_score=resume_score,
            detected_skills=json.dumps(resume_skills),
            matching_skills=json.dumps(matching_skills),
            missing_skills=json.dumps(missing_skills),
            candidate_rank=None,

            # STEP 18.7 - Save interview questions
            interview_questions=json.dumps(interview_questions),
            score_breakdown=json.dumps(score_breakdown),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to save resume analysis history")

    return render_template(
        "index.html",
        upload_success=True,
        uploaded_filename=filename,
        extracted_text=text,
        job_description=job_description,
        highlighted_resume_text=highlighted_resume_text,
        highlighted_job_description=highlighted_job_description,
        resume_skills=resume_skills,
        job_skills=job_skills,
        matching_skills=matching_skills,
        missing_skills=missing_skills,
        resume_score=resume_score,
        score_breakdown=score_breakdown,
        targeted_recommendations=targeted_recommendations,
        suggestions=suggestions,
        ats_rating=ats_rating,
        resume_strength=resume_strength,
        skill_gap_analysis=skill_gap_analysis,
        final_recommendation=final_recommendation,
        interview_questions=interview_questions,
        resume_info=resume_info,
    )


@app.route("/download-report", methods=["POST"])
@login_required
def download_report():
    report_data = {
        "filename": request.form.get("filename", "Resume"),
        "file_type": request.form.get("file_type", "Unknown"),
        "file_size": request.form.get("file_size", "Unknown"),
        "word_count": request.form.get("word_count", "0"),
        "resume_score": request.form.get("resume_score", "0"),
        "skills_score": int(
            request.form.get("skills_score", 0)
        ),
        "experience_score": int(
            request.form.get("experience_score", 0)
        ),
        "education_score": int(
            request.form.get("education_score", 0)
        ),
        "projects_score": int(
            request.form.get("projects_score", 0)
        ),
        "ats_label": request.form.get("ats_label", "Not available"),
        "strength_score": request.form.get("strength_score", "0"),
        "strength_label": request.form.get("strength_label", "Not available"),
        "final_title": request.form.get("final_title", "Resume Analysis"),
        "final_message": request.form.get("final_message", ""),
        "next_action": request.form.get("next_action", ""),
        "matching_skills": safe_json_list(
            request.form.get("matching_skills")
        ),
        "missing_skills": safe_json_list(
            request.form.get("missing_skills")
        ),
        "strong_areas": safe_json_list(
            request.form.get("strong_areas")
        ),
        "improvement_areas": safe_json_list(
            request.form.get("improvement_areas")
        ),
        "suggestions": safe_json_list(
            request.form.get("suggestions")),
        
        "technical_questions": safe_json_list(
            request.form.get("technical_questions")),

        "resume_questions": safe_json_list(
            request.form.get("resume_questions")),

        "job_questions": safe_json_list(
            request.form.get("job_questions")),
    }
    pdf_buffer = build_analysis_pdf(report_data)
    original_name = os.path.splitext(report_data["filename"])[0]
    safe_name = secure_filename(original_name) or "resume"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{safe_name}_analysis_report.pdf",
    )


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)