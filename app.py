import json
import os
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
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

# Maximum size allowed for one uploaded file: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Maximum complete request size: 100 MB
# Multiple-resume analysis can contain several 10 MB files.
MAX_REQUEST_SIZE = 100 * 1024 * 1024

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_SIZE

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

    interview_questions = db.Column(
        db.Text,
        nullable=False,
        default="{}",
    )
    
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
    Check whether the filename has an allowed extension.
    """

    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def extract_projects_section(resume_text):
    """Extract only the dedicated Projects section from a resume."""

    text = resume_text or ""
    project_headings = {
        "project",
        "projects",
        "academic projects",
        "personal projects",
        "technical projects",
        "key projects",
        "selected projects",
    }
    stopping_headings = {
        "education",
        "academic background",
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "skills",
        "technical skills",
        "certifications",
        "achievements",
        "summary",
        "objective",
        "languages",
        "publications",
        "interests",
    }

    project_lines = []
    collecting = False

    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue

        normalized_line = re.sub(
            r"[^a-z ]",
            " ",
            stripped_line.lower(),
        )
        normalized_line = re.sub(
            r"\s+",
            " ",
            normalized_line,
        ).strip()

        if normalized_line in project_headings:
            collecting = True
            continue

        if collecting and normalized_line in stopping_headings:
            break

        if collecting:
            project_lines.append(stripped_line)

    return "\n".join(project_lines)


def calculate_projects_relevance_score(
    resume_text,
    job_description,
    job_skills,
):
    """Calculate project relevance from the resume's Projects section."""

    text = resume_text or ""
    project_headings = {
        "project",
        "projects",
        "academic projects",
        "personal projects",
        "technical projects",
    }
    stopping_headings = {
        "education",
        "experience",
        "work experience",
        "professional experience",
        "skills",
        "technical skills",
        "certifications",
        "achievements",
        "summary",
        "objective",
        "languages",
        "publications",
        "interests",
    }

    project_lines = []
    collecting = False

    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue

        normalized_line = re.sub(
            r"[^a-z ]",
            "",
            stripped_line.lower(),
        ).strip()

        if normalized_line in project_headings:
            collecting = True
            continue

        if collecting and normalized_line in stopping_headings:
            break

        if collecting:
            project_lines.append(stripped_line)

    project_text = "\n".join(project_lines)
    if len(re.findall(r"\b\w+\b", project_text)) < 5:
        return 0

    project_lower = project_text.lower()
    score = 10

    matched_skills = sum(
        bool(re.search(
            rf"(?<!\w){re.escape(skill)}(?!\w)",
            project_text,
            flags=re.IGNORECASE,
        ))
        for skill in job_skills or []
    )
    if job_skills:
        score += round(matched_skills / len(job_skills) * 55)

    action_terms = (
        "built", "developed", "created", "designed", "implemented",
        "deployed", "automated", "trained", "analyzed", "optimized",
    )
    score += min(
        sum(
            bool(re.search(rf"\b{term}\b", project_lower))
            for term in action_terms
        ) * 4,
        16,
    )

    impact_pattern = (
        r"\b\d+(?:\.\d+)?\s*(?:%|users?|clients?|hours?|days?)\b"
    )
    if re.search(impact_pattern, project_lower):
        score += 10

    return max(0, min(100, round(score)))


def get_uploaded_file_size(uploaded_file):
    """
    Return the uploaded file size without saving it permanently.

    The stream is reset to the beginning so that Flask can save or
    process the file normally after validation.
    """

    try:
        uploaded_file.stream.seek(0, os.SEEK_END)
        file_size = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0)

        return file_size

    except (AttributeError, OSError):
        try:
            uploaded_file.stream.seek(0)
        except (AttributeError, OSError):
            pass

        return None


def has_valid_file_signature(uploaded_file, extension):
    """
    Verify that the actual file content matches its extension.

    This prevents a user from renaming files such as:
    image.jpg -> resume.pdf
    notes.txt -> resume.docx
    """

    try:
        uploaded_file.stream.seek(0)

        if extension == "pdf":
            header = uploaded_file.stream.read(5)
            uploaded_file.stream.seek(0)

            return header == b"%PDF-"

        if extension == "docx":
            if not zipfile.is_zipfile(uploaded_file.stream):
                uploaded_file.stream.seek(0)
                return False

            uploaded_file.stream.seek(0)

            with zipfile.ZipFile(uploaded_file.stream) as docx_archive:
                archive_files = set(docx_archive.namelist())

                required_files = {
                    "[Content_Types].xml",
                    "word/document.xml",
                }

                is_valid_docx = required_files.issubset(archive_files)

            uploaded_file.stream.seek(0)

            return is_valid_docx

        uploaded_file.stream.seek(0)
        return False

    except (
        AttributeError,
        OSError,
        zipfile.BadZipFile,
        RuntimeError,
    ):
        try:
            uploaded_file.stream.seek(0)
        except (AttributeError, OSError):
            pass

        return False


def validate_uploaded_file(
    uploaded_file,
    file_label="file",
):
    """
    Validate filename, extension, size and real file content.

    Returns:
        (safe_filename, extension, file_size, error_message)
    """

    if uploaded_file is None:
        return None, None, None, (
            f"No {file_label} was received."
        )

    original_filename = (uploaded_file.filename or "").strip()

    if not original_filename:
        return None, None, None, (
            f"Please select a {file_label}."
        )

    filename = secure_filename(original_filename)

    if not filename:
        return None, None, None, (
            f"The selected {file_label} has an invalid filename."
        )

    if not allowed_file(filename):
        return None, None, None, (
            f"The {file_label} must be a PDF or DOCX file."
        )

    extension = filename.rsplit(".", 1)[1].lower()
    file_size = get_uploaded_file_size(uploaded_file)

    if file_size is None:
        return None, None, None, (
            f"The size of the selected {file_label} could not be checked."
        )

    if file_size == 0:
        return None, None, None, (
            f"The selected {file_label} is empty. "
            "Please choose a valid PDF or DOCX file."
        )

    if file_size > MAX_FILE_SIZE:
        return None, None, None, (
            f"The selected {file_label} is larger than 10 MB. "
            "Please upload a smaller file."
        )

    if not has_valid_file_signature(uploaded_file, extension):
        return None, None, None, (
            f"The selected {file_label} is corrupted or its content "
            f"does not match the .{extension} extension."
        )

    uploaded_file.stream.seek(0)

    return filename, extension, file_size, None


def create_temporary_upload_path(filename, prefix):
    """
    Create a unique temporary path to prevent uploaded files
    from overwriting files with the same name.
    """

    unique_name = f"{prefix}_{uuid4().hex}_{filename}"

    return os.path.join(
        app.config["UPLOAD_FOLDER"],
        unique_name,
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


def find_term_contexts(
    text,
    term,
    window_size=140,
):
    """
    Find short text areas surrounding a term.

    Context helps determine whether a skill is merely listed
    or supported by project/experience evidence.
    """

    source_text = text or ""

    pattern = re.compile(
        rf"(?<!\w){re.escape(term)}(?!\w)",
        re.IGNORECASE,
    )

    contexts = []

    for match in pattern.finditer(source_text):
        start = max(
            0,
            match.start() - window_size,
        )

        end = min(
            len(source_text),
            match.end() + window_size,
        )

        contexts.append(
            source_text[start:end].lower()
        )

    return contexts


def calculate_job_skill_weight(
    job_description,
    skill,
):
    """
    Give more importance to required skills and less importance
    to optional/preferred skills.
    """

    skill_contexts = find_term_contexts(
        job_description,
        skill,
        window_size=120,
    )

    required_terms = [
        "required",
        "mandatory",
        "must have",
        "must-have",
        "proficient",
        "proficiency",
        "strong knowledge",
        "strong experience",
        "hands-on",
        "expertise",
        "essential",
    ]

    preferred_terms = [
        "preferred",
        "nice to have",
        "nice-to-have",
        "good to have",
        "added advantage",
        "plus",
        "optional",
    ]

    for context in skill_contexts:
        if any(
            term in context
            for term in required_terms
        ):
            return 1.35

    for context in skill_contexts:
        if any(
            term in context
            for term in preferred_terms
        ):
            return 0.75

    return 1.0


def calculate_resume_skill_evidence(
    resume_text,
    skill,
):
    """
    Calculate evidence strength for one job skill.

    Score meaning:
    - 0.00: skill not found
    - 0.60: skill mentioned only once
    - Higher values: repeated or supported by practical evidence
    - 1.00: strong practical evidence
    """

    skill_contexts = find_term_contexts(
        resume_text,
        skill,
        window_size=150,
    )

    if not skill_contexts:
        return 0.0

    # A detected skill receives basic credit.
    evidence_score = 0.60

    # Repeated use provides more confidence than one keyword.
    if len(skill_contexts) >= 2:
        evidence_score += 0.10

    practical_action_terms = [
        "built",
        "created",
        "developed",
        "designed",
        "implemented",
        "integrated",
        "deployed",
        "trained",
        "tested",
        "optimized",
        "analyzed",
        "automated",
        "managed",
        "used",
        "worked with",
        "responsible for",
        "contributed",
        "improved",
        "achieved",
    ]

    evidence_area_terms = [
        "project",
        "projects",
        "experience",
        "internship",
        "intern",
        "employment",
        "work history",
        "professional experience",
        "freelance",
        "research",
    ]

    has_practical_action = any(
        action_term in context
        for context in skill_contexts
        for action_term in practical_action_terms
    )

    has_evidence_area = any(
        area_term in context
        for context in skill_contexts
        for area_term in evidence_area_terms
    )

    if has_practical_action:
        evidence_score += 0.20

    if has_evidence_area:
        evidence_score += 0.10

    return min(
        evidence_score,
        1.0,
    )


def calculate_intelligent_skills_score(
    resume_text,
    job_description,
    job_skills,
):
    """
    Calculate a weighted and evidence-based skills score.

    Required skills receive more weight.
    Preferred skills receive slightly less weight.
    Resume skills with practical evidence receive more credit.
    """

    if not job_skills:
        return 0

    weighted_score = 0.0
    total_weight = 0.0

    for skill in job_skills:
        skill_weight = calculate_job_skill_weight(
            job_description,
            skill,
        )

        skill_evidence = calculate_resume_skill_evidence(
            resume_text,
            skill,
        )

        weighted_score += (
            skill_evidence * skill_weight
        )

        total_weight += skill_weight

    if total_weight == 0:
        return 0

    final_score = round(
        weighted_score / total_weight * 100
    )

    return max(
        0,
        min(100, final_score),
    )
    

def extract_experience_section(resume_text):
    """
    Extract only the candidate's experience-related section.

    Project descriptions are not automatically treated as
    professional experience.
    """

    text = resume_text or ""

    experience_headings = [
        "work experience",
        "professional experience",
        "employment history",
        "career history",
        "internship experience",
        "internships",
        "internship",
        "experience",
    ]

    stopping_headings = [
        "education",
        "projects",
        "skills",
        "technical skills",
        "certifications",
        "achievements",
        "summary",
        "objective",
        "languages",
        "publications",
        "interests",
    ]

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    section_lines = []
    collecting = False

    for line in lines:
        normalized_line = re.sub(
            r"[^a-z ]",
            "",
            line.lower(),
        ).strip()

        if normalized_line in experience_headings:
            collecting = True
            continue

        if (
            collecting
            and normalized_line in stopping_headings
        ):
            break

        if collecting:
            section_lines.append(line)

    return "\n".join(section_lines)


def extract_required_experience_years(job_description):
    """
    Detect the minimum number of experience years required by the JD.
    Examples: '2 years', '3+ years', '2-4 years'.
    """

    job_text = (job_description or "").lower()

    patterns = [
        r"(\d+)\s*\+\s*years?",
        r"minimum\s+of\s+(\d+)\s*years?",
        r"at\s+least\s+(\d+)\s*years?",
        r"(\d+)\s*-\s*\d+\s*years?",
        r"(\d+)\s+years?\s+of\s+experience",
    ]

    detected_years = []

    for pattern in patterns:
        matches = re.findall(
            pattern,
            job_text,
            flags=re.IGNORECASE,
        )

        detected_years.extend(
            int(match)
            for match in matches
        )

    if not detected_years:
        return 0

    return max(detected_years)


def extract_resume_experience_years(experience_text):
    """
    Detect explicitly mentioned experience duration from
    the candidate's experience section.
    """

    text = (experience_text or "").lower()

    patterns = [
        r"(\d+)\s*\+\s*years?",
        r"(\d+)\s+years?\s+of\s+experience",
        r"experience\s+of\s+(\d+)\s+years?",
    ]

    detected_years = []

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        detected_years.extend(
            int(match)
            for match in matches
        )

    if not detected_years:
        return 0

    return max(detected_years)


def calculate_experience_relevance_score(
    resume_text,
    job_description,
    job_skills,
):
    """
    Calculate experience relevance using real evidence:

    - An Experience or Internship section
    - Practical action statements
    - Relevant job skills
    - Role-related terms
    - Dates, duration and measurable achievements
    """

    experience_text = extract_experience_section(
        resume_text
    )

    # A project section alone must not receive
    # professional-experience credit.
    if not experience_text.strip():
        return 0

    experience_lower = experience_text.lower()

    word_count = len(
        re.findall(
            r"\b\w+\b",
            experience_text,
        )
    )

    # Reject an empty or extremely short section.
    if word_count < 5:
        return 0

    experience_score = 10

    # Give credit for a meaningful description.
    if word_count >= 15:
        experience_score += 10

    if word_count >= 35:
        experience_score += 5

    action_terms = [
        "developed",
        "built",
        "created",
        "designed",
        "implemented",
        "integrated",
        "deployed",
        "managed",
        "maintained",
        "tested",
        "optimized",
        "automated",
        "analyzed",
        "trained",
        "led",
        "collaborated",
        "improved",
        "resolved",
        "delivered",
        "supported",
    ]

    detected_actions = {
        action
        for action in action_terms
        if re.search(
            rf"\b{re.escape(action)}\b",
            experience_lower,
        )
    }

    # Maximum action-evidence contribution: 20 points.
    experience_score += min(
        len(detected_actions) * 5,
        20,
    )

    # Compare JD skills with the actual experience section.
    if job_skills:
        relevant_skills = [
            skill
            for skill in job_skills
            if re.search(
                rf"(?<!\w){re.escape(skill)}(?!\w)",
                experience_text,
                flags=re.IGNORECASE,
            )
        ]

        skill_relevance_ratio = (
            len(relevant_skills) /
            len(job_skills)
        )

        experience_score += round(
            skill_relevance_ratio * 35
        )

    role_terms = [
        "developer",
        "engineer",
        "analyst",
        "intern",
        "consultant",
        "specialist",
        "associate",
        "researcher",
        "freelancer",
    ]

    if any(
        re.search(
            rf"\b{re.escape(role)}\b",
            experience_lower,
        )
        for role in role_terms
    ):
        experience_score += 5

    # Detect employment dates such as 2023-2024 or Jan 2024.
    has_date_evidence = bool(
        re.search(
            r"\b(?:19|20)\d{2}\b",
            experience_text,
        )
        or re.search(
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
            r"[a-z]*\s+(?:19|20)\d{2}\b",
            experience_text,
            flags=re.IGNORECASE,
        )
    )

    if has_date_evidence:
        experience_score += 5

    # Detect achievements such as 20%, 500 users or 3 systems.
    has_measurable_result = bool(
        re.search(
            r"\b\d+(?:\.\d+)?\s*(?:%|users?|clients?|projects?|"
            r"applications?|systems?|hours?|days?|months?)\b",
            experience_lower,
        )
    )

    if has_measurable_result:
        experience_score += 10

    required_years = extract_required_experience_years(
        job_description
    )

    resume_years = extract_resume_experience_years(
        experience_text
    )

    if required_years > 0:
        if resume_years >= required_years:
            experience_score += 10

        elif resume_years > 0:
            experience_score += round(
                resume_years /
                required_years *
                10
            )

    # Prevent weak evidence from receiving an automatic 100%.
    return max(
        0,
        min(95, round(experience_score)),
    )
    
    
def extract_education_section(resume_text):
    """
    Extract only the Education section from the resume.
    """

    text = resume_text or ""

    education_headings = [
        "education",
        "academic background",
        "academic qualifications",
        "educational qualifications",
        "qualifications",
    ]

    stopping_headings = [
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "projects",
        "skills",
        "technical skills",
        "certifications",
        "achievements",
        "summary",
        "objective",
        "languages",
        "interests",
    ]

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    section_lines = []
    collecting = False

    for line in lines:
        normalized_line = re.sub(
            r"[^a-z ]",
            " ",
            line.lower(),
        )

        normalized_line = re.sub(
            r"\s+",
            " ",
            normalized_line,
        ).strip()

        if normalized_line in education_headings:
            collecting = True
            continue

        if (
            collecting
            and normalized_line in stopping_headings
        ):
            break

        if collecting:
            section_lines.append(line)

    return "\n".join(section_lines)


def detect_degree_level(text):
    """
    Detect the highest degree level mentioned in text.

    Level:
    4 = Doctorate
    3 = Master's
    2 = Bachelor's
    1 = Diploma/Associate
    0 = No recognised degree
    """

    source_text = (text or "").lower()

    degree_levels = {
        4: [
            r"\bph\.?\s*d\b",
            r"\bdoctorate\b",
            r"\bdoctoral\b",
        ],
        3: [
            r"\bm\.?\s*tech\b",
            r"\bmtech\b",
            r"\bm\.?\s*sc\b",
            r"\bmsc\b",
            r"\bm\.?\s*ca\b",
            r"\bmca\b",
            r"\bmaster(?:'s)?\b",
        ],
        2: [
            r"\bb\.?\s*tech\b",
            r"\bbtech\b",
            r"\bb\.?\s*e\b",
            r"\bb\.?\s*sc\b",
            r"\bbsc\b",
            r"\bb\.?\s*ca\b",
            r"\bbca\b",
            r"\bbachelor(?:'s)?\b",
            r"\bundergraduate degree\b",
        ],
        1: [
            r"\bdiploma\b",
            r"\bassociate degree\b",
            r"\bpolytechnic\b",
        ],
    }

    for level in sorted(
        degree_levels,
        reverse=True,
    ):
        if any(
            re.search(pattern, source_text)
            for pattern in degree_levels[level]
        ):
            return level

    return 0


def detect_education_fields(text):
    """
    Detect education specialisations or study fields.
    """

    source_text = (text or "").lower()

    education_fields = {
        "computer science": [
            "computer science",
            "computer engineering",
            "computer applications",
            "cse",
        ],
        "information technology": [
            "information technology",
            "information systems",
        ],
        "artificial intelligence": [
            "artificial intelligence",
            "ai and machine learning",
            "ai & machine learning",
            "aiml",
        ],
        "machine learning": [
            "machine learning",
            "ml engineering",
        ],
        "data science": [
            "data science",
            "data analytics",
        ],
        "electronics": [
            "electronics",
            "electrical engineering",
            "ece",
            "eee",
        ],
        "engineering": [
            "engineering",
            "technology",
        ],
        "mathematics": [
            "mathematics",
            "statistics",
        ],
    }

    detected_fields = set()

    for field_name, aliases in education_fields.items():
        if any(
            alias in source_text
            for alias in aliases
        ):
            detected_fields.add(field_name)

    return detected_fields


def calculate_education_match_score(
    resume_text,
    job_description,
    job_skills,
):
    """
    Calculate education relevance using:

    - Education-section evidence
    - Required degree level
    - Relevant study field
    - Coursework and technical subjects
    - Academic achievement evidence
    """

    education_text = extract_education_section(
        resume_text
    )

    if not education_text.strip():
        return 0

    education_words = re.findall(
        r"\b\w+\b",
        education_text,
    )

    # Reject empty or meaningless Education sections.
    if len(education_words) < 3:
        return 0

    resume_degree_level = detect_degree_level(
        education_text
    )

    required_degree_level = detect_degree_level(
        job_description
    )

    resume_fields = detect_education_fields(
        education_text
    )

    required_fields = detect_education_fields(
        job_description
    )

    education_score = 10

    # --------------------------------------
    # DEGREE-LEVEL RELEVANCE
    # --------------------------------------

    if required_degree_level > 0:
        if resume_degree_level >= required_degree_level:
            education_score += 45

        elif (
            resume_degree_level > 0
            and resume_degree_level ==
            required_degree_level - 1
        ):
            # Partial credit when the degree is one level below.
            education_score += 20

    elif resume_degree_level > 0:
        # The JD does not specify a degree, but the candidate
        # still receives moderate education evidence credit.
        education_score += 30

    # --------------------------------------
    # STUDY-FIELD RELEVANCE
    # --------------------------------------

    if required_fields:
        matching_fields = (
            resume_fields & required_fields
        )

        field_match_ratio = (
            len(matching_fields) /
            len(required_fields)
        )

        education_score += round(
            field_match_ratio * 25
        )

    elif resume_fields:
        education_score += 15

    # --------------------------------------
    # RELEVANT COURSEWORK AND SKILLS
    # --------------------------------------

    education_skill_matches = []

    for skill in job_skills or []:
        if re.search(
            rf"(?<!\w){re.escape(skill)}(?!\w)",
            education_text,
            flags=re.IGNORECASE,
        ):
            education_skill_matches.append(skill)

    if job_skills:
        coursework_ratio = (
            len(education_skill_matches) /
            len(job_skills)
        )

        education_score += round(
            coursework_ratio * 15
        )

    coursework_terms = [
        "coursework",
        "relevant coursework",
        "subjects",
        "curriculum",
        "academic project",
        "capstone",
        "thesis",
        "research",
    ]

    if any(
        term in education_text.lower()
        for term in coursework_terms
    ):
        education_score += 5

    # --------------------------------------
    # ACADEMIC EVIDENCE
    # --------------------------------------

    has_academic_result = bool(
        re.search(
            r"\b(?:cgpa|gpa)\s*[:\-]?\s*\d+(?:\.\d+)?",
            education_text,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"\b\d+(?:\.\d+)?\s*%",
            education_text,
        )
    )

    if has_academic_result:
        education_score += 5

    return max(
        0,
        min(95, round(education_score)),
    )


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

    # --------------------------------------
    # 1. SKILLS MATCH SCORE
    # --------------------------------------

    skills_score = calculate_intelligent_skills_score(
        resume_text,
        job_description,
        job_skills,
    )

    # --------------------------------------
    # 2. EXPERIENCE RELEVANCE SCORE
    # --------------------------------------

    experience_score = calculate_experience_relevance_score(
        resume_text,
        job_description,
        job_skills,
    )

    # --------------------------------------
    # 3. EDUCATION MATCH SCORE
    # --------------------------------------
    education_score = calculate_education_match_score(
        resume_text,
        job_description,
        job_skills,
    )

    # --------------------------------------
    # 4. PROJECTS RELEVANCE SCORE
    # --------------------------------------

    projects_score = calculate_projects_relevance_score(
        resume_text,
        job_description,
        job_skills,
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


def calculate_weighted_overall_score(score_breakdown):
    """
    Calculate the final resume score using the four improved
    category scores.

    Final weights:
    Skills: 40%
    Experience: 30%
    Projects: 20%
    Education: 10%
    """

    category_weights = {
        "skills": 0.40,
        "experience": 0.30,
        "projects": 0.20,
        "education": 0.10,
    }

    weighted_score = sum(
        max(
            0,
            min(
                100,
                score_breakdown.get(category, 0),
            ),
        ) * weight
        for category, weight in category_weights.items()
    )

    final_score = round(weighted_score)

    return max(
        0,
        min(100, final_score),
    )


def generate_candidate_strengths(
    score_breakdown,
    matching_skills,
):
    """
    Generate concise recruiter-facing strengths using only
    evidence already detected by the scoring system.
    """

    scores = {
        "skills": score_breakdown.get("skills", 0),
        "experience": score_breakdown.get("experience", 0),
        "education": score_breakdown.get("education", 0),
        "projects": score_breakdown.get("projects", 0),
    }

    clean_matching_skills = [
        str(skill).strip()
        for skill in matching_skills or []
        if str(skill).strip()
    ]

    strengths = []

    if clean_matching_skills:
        highlighted_skills = ", ".join(
            clean_matching_skills[:5]
        )
        strengths.append(
            f"Matches {len(clean_matching_skills)} priority job "
            f"skill(s), including {highlighted_skills}."
        )

    if scores["skills"] >= 75:
        strengths.append(
            f"Strong technical alignment with a "
            f"{scores['skills']}% skills-match score."
        )

    if scores["experience"] >= 65:
        strengths.append(
            f"Relevant professional evidence produced a "
            f"{scores['experience']}% experience score."
        )

    if scores["education"] >= 65:
        strengths.append(
            f"Education and qualifications align well with "
            f"the role at {scores['education']}%."
        )

    if scores["projects"] >= 65:
        strengths.append(
            f"Relevant project evidence demonstrates practical "
            f"ability with a {scores['projects']}% project score."
        )

    if not strengths:
        category_labels = {
            "skills": "Technical skills",
            "experience": "Experience",
            "education": "Education",
            "projects": "Projects",
        }

        strongest_category = max(
            scores,
            key=scores.get,
        )

        strongest_score = scores[strongest_category]

        if strongest_score > 0:
            strengths.append(
                f"{category_labels[strongest_category]} is the "
                f"candidate's strongest current area at "
                f"{strongest_score}%."
            )
        else:
            strengths.append(
                "No strong role-specific evidence was detected; "
                "manual recruiter review is recommended."
            )

    return strengths[:4]


def generate_candidate_weaknesses(
    score_breakdown,
    missing_skills,
):
    """
    Generate evidence-based weaknesses for recruiter review.
    """

    scores = {
        "skills": score_breakdown.get("skills", 0),
        "experience": score_breakdown.get("experience", 0),
        "education": score_breakdown.get("education", 0),
        "projects": score_breakdown.get("projects", 0),
    }

    clean_missing_skills = [
        str(skill).strip()
        for skill in missing_skills or []
        if str(skill).strip()
    ]

    weaknesses = []

    if clean_missing_skills:
        priority_missing_skills = ", ".join(
            clean_missing_skills[:5]
        )

        weaknesses.append(
            f"Missing {len(clean_missing_skills)} important job "
            f"skill(s), including {priority_missing_skills}."
        )

    if scores["skills"] < 50:
        weaknesses.append(
            f"Technical skill alignment is currently low at "
            f"{scores['skills']}%."
        )

    if scores["experience"] < 50:
        if scores["experience"] == 0:
            weaknesses.append(
                "No strong role-relevant professional experience "
                "evidence was detected."
            )
        else:
            weaknesses.append(
                f"Professional experience has limited relevance "
                f"to this role at {scores['experience']}%."
            )

    if scores["education"] < 50:
        if scores["education"] == 0:
            weaknesses.append(
                "No clearly relevant education or qualification "
                "evidence was detected."
            )
        else:
            weaknesses.append(
                f"Education alignment is currently limited at "
                f"{scores['education']}%."
            )

    if scores["projects"] < 50:
        if scores["projects"] == 0:
            weaknesses.append(
                "No strong role-relevant project evidence "
                "was detected."
            )
        else:
            weaknesses.append(
                f"Project relevance is currently limited at "
                f"{scores['projects']}%."
            )

    if not weaknesses:
        weaknesses.append(
            "No major weaknesses were detected. The recruiter "
            "should verify the candidate's claims during interview."
        )

    return weaknesses[:4]


def generate_hiring_recommendation(
    match_score,
    score_breakdown,
):
    """
    Generate a recruiter-friendly hiring recommendation using
    the weighted overall score and category scores.
    """

    skills_score = score_breakdown.get("skills", 0)
    experience_score = score_breakdown.get("experience", 0)
    projects_score = score_breakdown.get("projects", 0)

    if (
        match_score >= 80
        and skills_score >= 70
        and experience_score >= 60
    ):
        return {
            "label": "Strong Match",
            "css_class": "strong-match",
            "icon": "✅",
            "message": (
                "Recommended for interview. The candidate has "
                "strong overall alignment with the role."
            ),
        }

    if match_score >= 60:
        return {
            "label": "Potential Match",
            "css_class": "potential-match",
            "icon": "👍",
            "message": (
                "Consider for interview after reviewing the "
                "candidate's weaker scoring categories."
            ),
        }

    if (
        match_score >= 40
        or skills_score >= 50
        or experience_score >= 50
        or projects_score >= 50
    ):
        return {
            "label": "Needs Review",
            "css_class": "needs-review",
            "icon": "🔍",
            "message": (
                "Manual recruiter review is recommended before "
                "making an interview decision."
            ),
        }

    return {
        "label": "Low Match",
        "css_class": "low-match",
        "icon": "❌",
        "message": (
            "Not recommended for this role based on the current "
            "resume and job-description evidence."
        ),
    }


def generate_targeted_recommendations(
    score_breakdown,
    missing_skills,
):
    """
    Generate category-specific and prioritized recommendations.

    Recommendations use:
    - Category scores
    - Missing job skills
    - Category importance in the weighted overall score
    """

    scores = {
        "skills": score_breakdown.get("skills", 0),
        "experience": score_breakdown.get("experience", 0),
        "education": score_breakdown.get("education", 0),
        "projects": score_breakdown.get("projects", 0),
    }

    category_weights = {
        "skills": 0.40,
        "experience": 0.30,
        "projects": 0.20,
        "education": 0.10,
    }

    clean_missing_skills = [
        str(skill).strip()
        for skill in missing_skills or []
        if str(skill).strip()
    ]

    priority_skills = clean_missing_skills[:5]

    if priority_skills:
        missing_skills_text = ", ".join(
            priority_skills
        )
    else:
        missing_skills_text = ""

    recommendations = []

    # --------------------------------------
    # 1. SKILLS RECOMMENDATION
    # --------------------------------------

    skills_score = scores["skills"]

    if skills_score == 0:
        if missing_skills_text:
            skills_message = (
                "No strong evidence was found for the main job skills. "
                f"Add genuine knowledge or practical evidence for: "
                f"{missing_skills_text}. Do not add skills you have "
                "not actually learned or used."
            )
        else:
            skills_message = (
                "No clear job-relevant technical skills were detected. "
                "Create a dedicated Skills section and support important "
                "skills with project or experience evidence."
            )

    elif skills_score < 50:
        if missing_skills_text:
            skills_message = (
                f"Your skills alignment is currently low. Prioritize "
                f"learning and demonstrating: {missing_skills_text}. "
                "Show each genuine skill inside a project, internship "
                "or achievement statement."
            )
        else:
            skills_message = (
                "Your resume mentions some relevant skills, but the "
                "evidence is weak. Describe where and how you used each "
                "important technology."
            )

    elif skills_score < 80:
        if missing_skills_text:
            skills_message = (
                f"Your skills match is promising. To improve it, focus "
                f"on the remaining requirements: {missing_skills_text}. "
                "Add practical evidence instead of listing keywords only."
            )
        else:
            skills_message = (
                "Most required skills are present. Strengthen the score "
                "by connecting those skills to specific responsibilities, "
                "projects and measurable results."
            )

    else:
        if missing_skills_text:
            skills_message = (
                f"Your technical alignment is strong. The remaining "
                f"gaps are: {missing_skills_text}. Address only the "
                "skills that are genuinely relevant to your background."
            )
        else:
            skills_message = (
                "Your technical skills are strongly aligned with the "
                "job. Keep the most important skills visible and support "
                "them with recent practical evidence."
            )

    recommendations.append({
        "category": "Skills",
        "icon": "💻",
        "score": skills_score,
        "message": skills_message,
        "priority_impact": round(
            (100 - skills_score) *
            category_weights["skills"],
            2,
        ),
    })

    # --------------------------------------
    # 2. EXPERIENCE RECOMMENDATION
    # --------------------------------------

    experience_score = scores["experience"]

    if experience_score == 0:
        experience_message = (
            "No professional Experience or Internship section was "
            "detected. Add internships, freelance work, training or "
            "practical responsibilities with role names, dates, "
            "technologies used and outcomes."
        )

    elif experience_score < 50:
        experience_message = (
            "Your experience evidence is limited. Clearly mention your "
            "role, organization, employment dates and responsibilities. "
            "Connect the work directly to the job's required skills."
        )

    elif experience_score < 80:
        experience_message = (
            "Your experience is partly relevant. Improve it with strong "
            "action verbs and measurable achievements such as performance "
            "improvements, users supported or tasks automated."
        )

    else:
        experience_message = (
            "Your experience is strongly relevant. Keep the best "
            "achievements near the top and quantify their impact with "
            "percentages, time saved, users or delivered applications."
        )

    recommendations.append({
        "category": "Experience",
        "icon": "💼",
        "score": experience_score,
        "message": experience_message,
        "priority_impact": round(
            (100 - experience_score) *
            category_weights["experience"],
            2,
        ),
    })

    # --------------------------------------
    # 3. EDUCATION RECOMMENDATION
    # --------------------------------------

    education_score = scores["education"]

    if education_score == 0:
        education_message = (
            "No usable Education section was detected. Add your degree, "
            "specialization, institution, study period and relevant "
            "coursework or academic achievements."
        )

    elif education_score < 50:
        education_message = (
            "Your education has limited alignment with this role. "
            "Highlight relevant coursework, certifications, academic "
            "projects and technical subjects without changing your "
            "actual degree information."
        )

    elif education_score < 80:
        education_message = (
            "Your degree level is useful, but the field or coursework "
            "is only partly aligned. Add relevant subjects, certifications "
            "and academic work connected to the job."
        )

    else:
        education_message = (
            "Your education is strongly aligned. Keep the degree, "
            "specialization, CGPA and most relevant coursework clear "
            "and easy for recruiters to scan."
        )

    recommendations.append({
        "category": "Education",
        "icon": "🎓",
        "score": education_score,
        "message": education_message,
        "priority_impact": round(
            (100 - education_score) *
            category_weights["education"],
            2,
        ),
    })

    # --------------------------------------
    # 4. PROJECTS RECOMMENDATION
    # --------------------------------------

    projects_score = scores["projects"]

    if projects_score == 0:
        if missing_skills_text:
            projects_message = (
                "No genuine Projects section was detected. Build or add "
                f"a relevant project that honestly demonstrates some of "
                f"these job requirements: {missing_skills_text}. Include "
                "the problem, your contribution, technologies and result."
            )
        else:
            projects_message = (
                "No genuine Projects section was detected. Add a relevant "
                "project explaining the problem, your contribution, "
                "technologies used and measurable outcome."
            )

    elif projects_score < 50:
        projects_message = (
            "Your projects have limited job relevance. Improve their "
            "descriptions by explaining what you built, your individual "
            "contribution, the technologies used and the final outcome."
        )

    elif projects_score < 80:
        if missing_skills_text:
            projects_message = (
                f"Your projects provide useful evidence. Strengthen them "
                f"with measurable results and, where truthful, demonstrate "
                f"these remaining skills: {missing_skills_text}."
            )
        else:
            projects_message = (
                "Your projects are relevant. Strengthen them with metrics "
                "such as accuracy, response time, users, records processed "
                "or performance improvements."
            )

    else:
        projects_message = (
            "Your projects are strongly relevant. Keep the best project "
            "first and clearly show its technologies, architecture, your "
            "contribution and measurable result."
        )

    recommendations.append({
        "category": "Projects",
        "icon": "🚀",
        "score": projects_score,
        "message": projects_message,
        "priority_impact": round(
            (100 - projects_score) *
            category_weights["projects"],
            2,
        ),
    })

    # Display the recommendation with the greatest possible
    # effect on the weighted overall score first.
    recommendations.sort(
        key=lambda item: item["priority_impact"],
        reverse=True,
    )

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


def generate_interview_questions(
    resume_text,
    job_description,
    resume_skills,
    matching_skills,
    missing_skills,
    job_skills,
):
    """
    Generate technical, project/resume, skill-gap and role/JD questions.
    """

    technical_questions = []
    resume_questions = []
    job_questions = []

    def add_unique(question_list, question):
        clean_question = str(question).strip()
        if clean_question and clean_question not in question_list:
            question_list.append(clean_question)

    role_patterns = [
        ("Python Developer", ["python developer"]),
        ("Backend Developer", ["backend developer", "back-end developer"]),
        ("Frontend Developer", ["frontend developer", "front-end developer"]),
        (
            "Full Stack Developer",
            ["full stack developer", "full-stack developer"],
        ),
        (
            "Machine Learning Engineer",
            ["machine learning engineer", "ml engineer"],
        ),
        ("AI Engineer", ["ai engineer", "artificial intelligence engineer"]),
        ("Data Scientist", ["data scientist"]),
        ("Data Analyst", ["data analyst"]),
        ("Software Engineer", ["software engineer"]),
        ("DevOps Engineer", ["devops engineer"]),
        ("Cloud Engineer", ["cloud engineer"]),
        ("Web Developer", ["web developer"]),
    ]

    job_lower = (job_description or "").lower()
    target_role = "this role"
    for role_name, aliases in role_patterns:
        if any(alias in job_lower for alias in aliases):
            target_role = role_name
            break

    skill_question_bank = {
        "python": [
            (
                "Explain the difference between a Python list, tuple, set and "
                "dictionary."
            ),
            (
                "How do you handle exceptions and debug errors in a Python "
                "application?"
            ),
        ],
        "flask": [
            "Explain the request-response lifecycle in a Flask application.",
            (
                "How would you structure and secure a production Flask "
                "application?"
            ),
        ],
        "sql": [
            (
                "Explain the difference between INNER JOIN and LEFT JOIN with "
                "an example."
            ),
            (
                "How do indexes improve SQL query performance, and when can "
                "they become costly?"
            ),
        ],
        "rest api": [
            (
                "What makes an API RESTful, and which HTTP methods support "
                "CRUD operations?"
            ),
            (
                "How would you handle authentication, validation and errors "
                "in a REST API?"
            ),
        ],
        "aws": [
            (
                "Which AWS services would you use to deploy a Flask "
                "application and why?"
            ),
            (
                "How would you monitor, secure and scale an application "
                "deployed on AWS?"
            ),
        ],
        "mongodb": [
            "When would you choose MongoDB instead of a relational database?",
            (
                "How would you design indexes for a frequently queried "
                "MongoDB collection?"
            ),
        ],
        "machine learning": [
            (
                "How do you detect and reduce overfitting in a "
                "machine-learning model?"
            ),
            (
                "Which evaluation metrics suit an imbalanced classification "
                "problem?"
            ),
        ],
        "react": [
            "Explain React state, props and the purpose of hooks.",
            "How would you prevent unnecessary component re-renders?",
        ],
        "javascript": [
            "Explain promises, async/await and error handling in JavaScript.",
        ],
        "docker": [
            (
                "How would you containerize a Python web application using "
                "Docker?"
            ),
        ],
        "git": [
            (
                "Explain your Git workflow when collaborating with a "
                "development team."
            ),
        ],
    }

    for skill in matching_skills[:6]:
        questions = skill_question_bank.get(skill.lower())
        if questions:
            for question in questions[:2]:
                add_unique(technical_questions, question)
        else:
            add_unique(
                technical_questions,
                f"Explain a practical problem you solved using {skill} and "
                "why you selected it.",
            )
            add_unique(
                technical_questions,
                f"What are the important concepts, limitations and best "
                f"practices in {skill}?",
            )

    if not technical_questions:
        add_unique(
            technical_questions,
            (
                "Which technical skill is your strongest, and how have you "
                "applied it?"
            ),
        )
        add_unique(
            technical_questions,
            "How do you approach debugging an unfamiliar technical problem?",
        )

    projects_text = extract_projects_section(resume_text or "")
    experience_text = extract_experience_section(resume_text or "")
    project_skill_matches = [
        skill
        for skill in job_skills or []
        if re.search(
            rf"(?<!\w){re.escape(skill)}(?!\w)",
            projects_text,
            flags=re.IGNORECASE,
        )
    ]

    if projects_text.strip():
        if project_skill_matches:
            project_skill_text = ", ".join(project_skill_matches[:5])
            add_unique(
                resume_questions,
                f"Choose one project where you used {project_skill_text}. "
                "Explain its architecture and your contribution.",
            )
        else:
            add_unique(
                resume_questions,
                (
                    "Choose the project most relevant to this job and explain "
                    "its "
                    "architecture and your contribution."
                ),
            )
        add_unique(
            resume_questions,
            (
                "What was the most difficult technical problem in that "
                "project, and how did you solve it?"
            ),
        )
        add_unique(
            resume_questions,
            (
                "How did you test the project and measure whether it solved "
                "the original problem?"
            ),
        )
        add_unique(
            resume_questions,
            (
                "If you rebuilt the project today, what improvements would "
                "you make?"
            ),
        )
    else:
        add_unique(
            resume_questions,
            (
                "Your resume has no dedicated Projects section. Describe one "
                "practical or academic project that demonstrates your ability."
            ),
        )
        add_unique(
            resume_questions,
            (
                "What was your individual contribution, and which "
                "parts did you implement yourself?"
            ),
        )

    if experience_text.strip():
        add_unique(
            resume_questions,
            (
                "Describe your most relevant professional responsibility and "
                "how it "
                "prepared you for this position."
            ),
        )
        add_unique(
            resume_questions,
            (
                "Which measurable achievement from your experience are you "
                "most proud of?"
            ),
        )

    for skill in resume_skills[:3]:
        add_unique(
            resume_questions,
            (
                f"Your resume mentions {skill}. Where did you use it, "
                "what did you build, and what result did you "
                "achieve?"
            ),
        )

    for skill in missing_skills[:5]:
        add_unique(
            job_questions,
            (
                f"This {target_role} position requires {skill}. What do you "
                "currently understand about it?"
            ),
        )
        add_unique(
            job_questions,
            (
                f"If you needed {skill} in your first month, how would "
                "you learn and apply it?"
            ),
        )

    add_unique(
        job_questions,
        (
            f"Why are you interested in the {target_role} position, and what "
            "makes you suitable?"
        ),
    )
    if matching_skills:
        strongest_skills_text = ", ".join(matching_skills[:4])
        add_unique(
            job_questions,
            (
                f"This role values {strongest_skills_text}. How would you "
                "combine them to solve a business problem?"
            ),
        )
    add_unique(
        job_questions,
        f"What would be your plan for the first 30 days as a {target_role}?",
    )
    add_unique(
        job_questions,
        (
            "Which job-description requirement is most challenging for you, "
            "and how would you address it?"
        ),
    )

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


def build_multiple_resume_pdf(
    candidates,
    job_skills,
):
    """
    Build a recruiter-friendly multiple-resume PDF report.
    """

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=16 * mm,
        bottomMargin=22 * mm,
        title="Multiple Resume Recruiter Report",
        author="AI Resume Screener",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "MultipleReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=27,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "MultipleReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_CENTER,
        spaceAfter=18,
    )

    section_style = ParagraphStyle(
        "MultipleReportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0369A1"),
        spaceBefore=10,
        spaceAfter=8,
    )

    normal_style = ParagraphStyle(
        "MultipleReportNormal",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=5,
    )

    small_style = ParagraphStyle(
        "MultipleReportSmall",
        parent=normal_style,
        fontSize=8,
        leading=11,
    )

    story = [
        Paragraph("AI Resume Screener", title_style),
        Paragraph(
            "Multiple-Candidate Recruiter Report",
            subtitle_style,
        ),
        Paragraph(
            f"<b>Candidates analyzed:</b> {len(candidates)}",
            normal_style,
        ),
        Paragraph(
            f"<b>Job skills:</b> {create_skill_text(job_skills)}",
            normal_style,
        ),
        Spacer(1, 8),
        Paragraph("Candidate Comparison", section_style),
    ]

    comparison_data = [
        [
            "Rank",
            "Candidate",
            "Overall",
            "Skills",
            "Exp.",
            "Edu.",
            "Projects",
        ]
    ]

    for candidate in candidates:
        scores = candidate.get("score_breakdown", {})

        comparison_data.append(
            [
                f"#{candidate.get('rank', '-')}",
                Paragraph(
                    escape(
                        str(
                            candidate.get(
                                "filename",
                                "Candidate",
                            )
                        )
                    ),
                    small_style,
                ),
                f"{candidate.get('match_score', 0)}%",
                f"{scores.get('skills', 0)}%",
                f"{scores.get('experience', 0)}%",
                f"{scores.get('education', 0)}%",
                f"{scores.get('projects', 0)}%",
            ]
        )

    comparison_table = Table(
        comparison_data,
        repeatRows=1,
        colWidths=[
            12 * mm,
            55 * mm,
            20 * mm,
            18 * mm,
            18 * mm,
            18 * mm,
            20 * mm,
        ],
    )

    comparison_table.setStyle(
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
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
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
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#CBD5E1"),
                ),
                (
                    "BACKGROUND",
                    (0, 1),
                    (-1, 1),
                    colors.HexColor("#DCFCE7"),
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 2),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F8FAFC"),
                    ],
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
            ]
        )
    )

    story.append(comparison_table)

    for candidate in candidates:
        story.append(PageBreak())

        recommendation = candidate.get(
            "hiring_recommendation",
            {},
        )

        story.append(
            Paragraph(
                (
                    f"Rank #{candidate.get('rank', '-')} - "
                    f"{escape(str(candidate.get('filename', 'Candidate')))}"
                ),
                section_style,
            )
        )

        story.append(
            Paragraph(
                (
                    f"<b>Overall weighted score:</b> "
                    f"{candidate.get('match_score', 0)}%"
                ),
                normal_style,
            )
        )

        story.append(
            Paragraph(
                (
                    f"<b>Hiring recommendation:</b> "
                    f"{escape(str(recommendation.get(
                        'label', 'Needs Review'
                    )))}"
                ),
                normal_style,
            )
        )

        story.append(
            Paragraph(
                escape(
                    str(
                        recommendation.get(
                            "message",
                            "Manual recruiter review is recommended.",
                        )
                    )
                ),
                normal_style,
            )
        )

        story.append(
            Paragraph("<b>Matching skills</b>", normal_style)
        )
        story.append(
            Paragraph(
                create_skill_text(
                    candidate.get("matching_skills", [])
                ),
                normal_style,
            )
        )

        story.append(
            Paragraph("<b>Missing skills</b>", normal_style)
        )
        story.append(
            Paragraph(
                create_skill_text(
                    candidate.get("missing_skills", [])
                ),
                normal_style,
            )
        )

        story.append(
            Paragraph("Candidate Strengths", section_style)
        )

        for strength in candidate.get("strengths", []):
            story.append(
                Paragraph(
                    f"&bull; {escape(str(strength))}",
                    normal_style,
                )
            )

        story.append(
            Paragraph("Candidate Weaknesses", section_style)
        )

        for weakness in candidate.get("weaknesses", []):
            story.append(
                Paragraph(
                    f"&bull; {escape(str(weakness))}",
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
    """
    Handle uploads that exceed the complete request-size limit.
    """

    app.logger.warning(
        "Upload request exceeded the maximum size: %s",
        request.path,
    )

    if request.path.startswith("/multiple-resume"):
        flash(
            "The complete upload is too large. Each file must be "
            "10 MB or smaller, and the combined upload must be "
            "100 MB or smaller.",
            "danger",
        )

        return redirect(url_for("multiple_resume"))

    if current_user.is_authenticated:
        return render_template(
            "index.html",
            upload_error=(
                "The complete upload is too large. The resume and "
                "job-description files must each be 10 MB or smaller."
            ),
        ), 413

    flash(
        "The submitted request was too large. "
        "Please select smaller files.",
        "danger",
    )

    return redirect(url_for("login"))


@app.errorhandler(400)
def invalid_request(error):
    """
    Handle malformed or incomplete browser requests.
    """

    app.logger.warning(
        "Invalid request received for %s",
        request.path,
    )

    flash(
        "The submitted request was invalid or incomplete. "
        "Please check the form and try again.",
        "danger",
    )

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    return redirect(url_for("login"))


@app.errorhandler(404)
def page_not_found(error):
    """
    Show a friendly message when a page does not exist.
    """

    app.logger.info(
        "Page not found: %s",
        request.path,
    )

    flash(
        "The requested page could not be found.",
        "warning",
    )

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    return redirect(url_for("login"))


@app.errorhandler(500)
def internal_server_error(error):
    """
    Handle unexpected server or analysis failures safely.
    """

    db.session.rollback()

    app.logger.exception(
        "Unexpected server error while processing %s",
        request.path,
    )

    flash(
        "Something went wrong while processing your request. "
        "Your uploaded files were not permanently stored. "
        "Please try again.",
        "danger",
    )

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    return redirect(url_for("login"))


@app.route("/")
def landing():
    """Send visitors to the correct starting page."""

    if current_user.is_authenticated:
        return redirect(url_for("home"))

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

        try:
            analysis.score_breakdown_data = json.loads(
                analysis.score_breakdown or "{}"
            )
        except (json.JSONDecodeError, TypeError):
            analysis.score_breakdown_data = {}

        if analysis.analysis_type == "multiple":
            analysis.hiring_recommendation_data = (
                generate_hiring_recommendation(
                    analysis.match_score,
                    analysis.score_breakdown_data,
                )
            )
        else:
            analysis.hiring_recommendation_data = None

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

    try:
        score_breakdown = json.loads(
            analysis.score_breakdown or "{}"
        )
    except (json.JSONDecodeError, TypeError):
        score_breakdown = {}

    candidate_strengths = []
    candidate_weaknesses = []
    hiring_recommendation = None

    if analysis.analysis_type == "multiple":
        candidate_strengths = generate_candidate_strengths(
            score_breakdown,
            matching_skills,
        )

        candidate_weaknesses = generate_candidate_weaknesses(
            score_breakdown,
            missing_skills,
        )

        hiring_recommendation = generate_hiring_recommendation(
            analysis.match_score,
            score_breakdown,
        )

    return render_template(
        "analysis_details.html",
        analysis=analysis,
        matching_skills=matching_skills,
        missing_skills=missing_skills,
        detected_skills=detected_skills,
        interview_questions=interview_questions,
        score_breakdown=score_breakdown,
        candidate_strengths=candidate_strengths,
        candidate_weaknesses=candidate_weaknesses,
        hiring_recommendation=hiring_recommendation,
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
    """
    Get the job description from pasted text or an uploaded file.

    Validation includes:
    - Empty job description
    - Invalid extension
    - Empty file
    - File larger than 10 MB
    - Renamed or corrupted PDF/DOCX file
    - File with no readable text
    """

    job_description = (form_text or "").strip()

    has_uploaded_file = (
        uploaded_file is not None
        and bool((uploaded_file.filename or "").strip())
    )

    # The user must paste text or upload a job-description file.
    if not job_description and not has_uploaded_file:
        return None, (
            "Please paste the job description or upload a "
            "PDF/DOCX job-description file."
        )

    # If a file was uploaded, validate and extract text from it.
    if has_uploaded_file:
        (
            filename,
            extension,
            file_size,
            validation_error,
        ) = validate_uploaded_file(
            uploaded_file,
            file_label="job-description file",
        )

        if validation_error:
            return None, validation_error

        temporary_path = create_temporary_upload_path(
            filename,
            prefix,
        )

        try:
            uploaded_file.save(temporary_path)

            extracted_text = extract_resume_text(
                temporary_path,
                extension,
            ).strip()

            if not extracted_text:
                return None, (
                    "The uploaded job-description file contains no "
                    "readable text. It may be empty, image-based, "
                    "password-protected or corrupted."
                )

            job_description = extracted_text

        except (
            zipfile.BadZipFile,
            KeyError,
            ValueError,
            OSError,
        ) as error:
            app.logger.warning(
                "Invalid job-description file %s: %s",
                filename,
                error,
            )

            return None, (
                "The uploaded job-description file is corrupted, "
                "password-protected or not a valid PDF/DOCX document."
            )

        except Exception as error:
            app.logger.exception(
                "Job-description extraction failed for %s: %s",
                filename,
                error,
            )

            return None, (
                "The job-description file could not be processed. "
                "Please check the file and try again."
            )

        finally:
            if os.path.exists(temporary_path):
                try:
                    os.remove(temporary_path)
                except OSError:
                    app.logger.warning(
                        "Could not remove temporary job-description file: %s",
                        temporary_path,
                    )

    # Final check after pasted-text/file processing.
    if not job_description.strip():
        return None, (
            "The job description cannot be empty. "
            "Please provide the role, skills and requirements."
        )

    return job_description, None


@app.route("/multiple-resume")
@login_required
def multiple_resume():
    return render_template("multiple_resume.html")


@app.route("/multiple-resume/analyze", methods=["POST"])
@login_required
def analyze_multiple_resumes():
    """
    Validate, analyze, score and rank multiple resumes.
    """

    # Validate pasted or uploaded job description.
    job_description, job_error = extract_uploaded_jd(
        request.form.get("job_description", ""),
        request.files.get("job_description_file"),
        "multi_jd",
    )

    if job_error:
        flash(job_error, "danger")
        return redirect(url_for("multiple_resume"))

    job_skills = extract_skills(job_description)

    if not validate_detected_job_skills(job_skills):
        flash(
            "The job description contains no recognized skills. "
            "Please provide a more detailed job description.",
            "warning",
        )
        return redirect(url_for("multiple_resume"))

    job_skill_set = set(job_skills)

    # Receive all selected resume files.
    uploaded_files = request.files.getlist("resumes")

    valid_files = [
        uploaded_file
        for uploaded_file in uploaded_files
        if uploaded_file
        and (uploaded_file.filename or "").strip()
    ]

    if len(valid_files) < 2:
        flash(
            "Please upload at least two resumes for candidate comparison.",
            "warning",
        )
        return redirect(url_for("multiple_resume"))

    # Validate duplicate filenames.
    uploaded_names = [
        secure_filename(uploaded_file.filename).lower()
        for uploaded_file in valid_files
    ]

    if len(uploaded_names) != len(set(uploaded_names)):
        flash(
            "Duplicate resume filenames were detected. "
            "Please rename the duplicate files and upload them again.",
            "warning",
        )
        return redirect(url_for("multiple_resume"))

    validated_files = []

    # Validate every file before analyzing any candidate.
    for uploaded_file in valid_files:
        original_name = (
            uploaded_file.filename or "selected file"
        ).strip()

        (
            filename,
            extension,
            file_size,
            validation_error,
        ) = validate_uploaded_file(
            uploaded_file,
            file_label=f"resume '{original_name}'",
        )

        if validation_error:
            flash(validation_error, "danger")
            return redirect(url_for("multiple_resume"))

        validated_files.append(
            {
                "uploaded_file": uploaded_file,
                "filename": filename,
                "extension": extension,
                "file_size": file_size,
            }
        )

    candidates = []

    # Extract and analyze every validated resume.
    for validated_file in validated_files:
        uploaded_file = validated_file["uploaded_file"]
        filename = validated_file["filename"]
        extension = validated_file["extension"]
        file_size = validated_file["file_size"]

        temporary_path = create_temporary_upload_path(
            filename,
            "multiple_resume",
        )

        try:
            uploaded_file.save(temporary_path)

            text = extract_resume_text(
                temporary_path,
                extension,
            ).strip()

        except (
            zipfile.BadZipFile,
            KeyError,
            ValueError,
            OSError,
        ) as error:
            app.logger.warning(
                "Invalid multiple-resume file %s: %s",
                filename,
                error,
            )

            flash(
                f"{filename} is corrupted, password-protected "
                "or not a valid PDF/DOCX document.",
                "danger",
            )
            return redirect(url_for("multiple_resume"))

        except Exception as error:
            app.logger.exception(
                "Multiple-resume processing failed for %s: %s",
                filename,
                error,
            )

            flash(
                f"{filename} could not be processed. "
                "Please check the file and try again.",
                "danger",
            )
            return redirect(url_for("multiple_resume"))

        finally:
            if os.path.exists(temporary_path):
                try:
                    os.remove(temporary_path)
                except OSError:
                    app.logger.warning(
                        "Could not remove temporary resume: %s",
                        temporary_path,
                    )

        if not text:
            flash(
                f"No readable text was found in {filename}. "
                "The file may be empty, image-based, "
                "password-protected or corrupted.",
                "warning",
            )
            return redirect(url_for("multiple_resume"))

        if len(text.split()) < 3:
            flash(
                f"{filename} does not contain enough readable "
                "text for analysis.",
                "warning",
            )
            return redirect(url_for("multiple_resume"))

        resume_skills = extract_skills(text)
        resume_skill_set = set(resume_skills)

        matching_skills = sorted(
            resume_skill_set & job_skill_set
        )

        missing_skills = sorted(
            job_skill_set - resume_skill_set
        )

        score_breakdown = calculate_score_breakdown(
            text,
            job_description,
            matching_skills,
            job_skills,
        )

        match_score = calculate_weighted_overall_score(
            score_breakdown
        )

        candidate_strengths = generate_candidate_strengths(
            score_breakdown,
            matching_skills,
        )
        
        candidate_weaknesses = generate_candidate_weaknesses(
            score_breakdown,
            missing_skills,
        )
        
        hiring_recommendation = generate_hiring_recommendation(
            match_score,
            score_breakdown,
        )

        candidate_interview_questions = generate_interview_questions(
            text,
            job_description,
            resume_skills,
            matching_skills,
            missing_skills,
            job_skills,
        )

        candidates.append(
            {
                "filename": filename,
                "file_type": extension.upper(),
                "file_size": file_size,
                "extracted_text": text,
                "word_count": len(text.split()),
                "character_count": len(text),
                "line_count": len(
                    [
                        line
                        for line in text.splitlines()
                        if line.strip()
                    ]
                ),
                "resume_skills": resume_skills,
                "matching_skills": matching_skills,
                "missing_skills": missing_skills,
                "match_score": match_score,
                "score_breakdown": score_breakdown,
                "strengths": candidate_strengths,
                "weaknesses": candidate_weaknesses,
                "hiring_recommendation": hiring_recommendation,
                "interview_questions": candidate_interview_questions,
            }
        )

    # Rank candidates from highest to lowest score.
    candidates.sort(
        key=lambda candidate: candidate["match_score"],
        reverse=True,
    )

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):
        candidate["rank"] = rank

    report_candidates = [
        {
            "rank": candidate["rank"],
            "filename": candidate["filename"],
            "match_score": candidate["match_score"],
            "score_breakdown": candidate["score_breakdown"],
            "matching_skills": candidate["matching_skills"],
            "missing_skills": candidate["missing_skills"],
            "strengths": candidate["strengths"],
            "weaknesses": candidate["weaknesses"],
            "hiring_recommendation": candidate[
                "hiring_recommendation"
            ],
        }
        for candidate in candidates
    ]

    # Save candidate results in history.
    try:
        for candidate in candidates:
            analysis = Analysis(
                user_id=current_user.id,
                resume_filename=candidate["filename"],
                analysis_type="multiple",
                job_description=job_description,
                match_score=candidate["match_score"],
                detected_skills=json.dumps(
                    candidate["resume_skills"]
                ),
                matching_skills=json.dumps(
                    candidate["matching_skills"]
                ),
                missing_skills=json.dumps(
                    candidate["missing_skills"]
                ),
                candidate_rank=candidate["rank"],
                score_breakdown=json.dumps(
                    candidate["score_breakdown"]
                ),
                interview_questions=json.dumps(
                    candidate["interview_questions"]
                ),
            )

            db.session.add(analysis)

        db.session.commit()

    except Exception as error:
        db.session.rollback()

        app.logger.exception(
            "Failed to save multiple-resume history: %s",
            error,
        )

        flash(
            "The candidates were analyzed, but their history "
            "could not be saved.",
            "warning",
        )

    return render_template(
        "multiple_resume.html",
        extraction_success=True,
        candidates=candidates,
        report_candidates=report_candidates,
        uploaded_names=[
            candidate["filename"]
            for candidate in candidates
        ],
        upload_success=True,
        job_description=job_description,
        job_skills=job_skills,
    )


@app.route("/upload", methods=["POST"])
@login_required
def upload_resume():
    # Get the uploaded resume from the form.
    uploaded_resume = request.files.get("resume")

    (
        filename,
        extension,
        file_size,
        validation_error,
    ) = validate_uploaded_file(
        uploaded_resume,
        file_label="resume",
    )

    if validation_error:
        return render_template(
            "index.html",
            upload_error=validation_error,
        )

    # Validate the pasted or uploaded job description.
    job_description, job_error = extract_uploaded_jd(
        request.form.get("job_description", ""),
        request.files.get("job_description_file"),
        "single_jd",
    )

    if job_error:
        return render_template(
            "index.html",
            upload_error=job_error,
        )

    # Use a unique temporary filename.
    temporary_path = create_temporary_upload_path(
        filename,
        "single_resume",
    )

    try:
        uploaded_resume.save(temporary_path)

        text = extract_resume_text(
            temporary_path,
            extension,
        ).strip()

    except (
        zipfile.BadZipFile,
        KeyError,
        ValueError,
        OSError,
    ) as error:
        app.logger.warning(
            "Invalid resume file %s: %s",
            filename,
            error,
        )

        return render_template(
            "index.html",
            upload_error=(
                "The uploaded resume is corrupted, "
                "password-protected or not a valid PDF/DOCX document."
            ),
        )

    except Exception as error:
        app.logger.exception(
            "Resume processing failed for %s: %s",
            filename,
            error,
        )

        return render_template(
            "index.html",
            upload_error=(
                "The resume could not be processed. "
                "Please check the file and try again."
            ),
        )

    finally:
        if os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                app.logger.warning(
                    "Could not remove temporary resume file: %s",
                    temporary_path,
                )

    # The file is structurally valid, but it may contain no text.
    if not text:
        return render_template(
            "index.html",
            upload_error=(
                "No readable text was found in the resume. "
                "The file may be empty, image-based, "
                "password-protected or corrupted."
            ),
        )

    # Reject files containing only a few unreadable characters.
    if len(text.split()) < 3:
        return render_template(
            "index.html",
            upload_error=(
                "The resume does not contain enough readable text "
                "for analysis. Please upload a complete resume."
            ),
        )

    # Create a readable file-size value for the result page.
    if file_size < 1024:
        formatted_size = f"{file_size} bytes"

    elif file_size < 1024 * 1024:
        formatted_size = f"{file_size / 1024:.2f} KB"

    else:
        formatted_size = (
            f"{file_size / (1024 * 1024):.2f} MB"
        )

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

    resume_set = set(resume_skills)
    job_set = set(job_skills)

    matching_skills = sorted(
        resume_set & job_set
    )

    missing_skills = sorted(
        job_set - resume_set
    )

    score_breakdown = calculate_score_breakdown(
        text,
        job_description,
        matching_skills,
        job_skills,
    )

    resume_score = calculate_weighted_overall_score(
        score_breakdown
    )

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

    targeted_recommendations = generate_targeted_recommendations(
        score_breakdown,
        missing_skills,
    )

    interview_questions = generate_interview_questions(
        text,
        job_description,
        resume_skills,
        matching_skills,
        missing_skills,
        job_skills,
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

            interview_questions=json.dumps(interview_questions),
            score_breakdown=json.dumps(score_breakdown),
        ))
        db.session.commit()
    except Exception as error:
        db.session.rollback()

        app.logger.exception(
            "Failed to save single-resume analysis history: %s",
            error,
        )

        flash(
            "Your resume was analyzed successfully, but the result "
            "could not be saved to Resume History. You can still "
            "view the current analysis.",
            "warning",
        )

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
            request.form.get("suggestions")
        ),
        "technical_questions": safe_json_list(
            request.form.get("technical_questions")
        ),
        "resume_questions": safe_json_list(
            request.form.get("resume_questions")
        ),
        "job_questions": safe_json_list(
            request.form.get("job_questions")
        ),
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


@app.route(
    "/download-multiple-report",
    methods=["POST"],
)
@login_required
def download_multiple_report():
    try:
        candidates = json.loads(
            request.form.get(
                "report_candidates",
                "[]",
            )
        )

        job_skills = json.loads(
            request.form.get(
                "report_job_skills",
                "[]",
            )
        )

    except (json.JSONDecodeError, TypeError):
        flash(
            "The recruiter report data is invalid. "
            "Please analyze the resumes again.",
            "danger",
        )
        return redirect(url_for("multiple_resume"))

    if not isinstance(candidates, list) or not candidates:
        flash(
            "No candidate results were found for the report.",
            "warning",
        )
        return redirect(url_for("multiple_resume"))

    valid_candidates = [
        candidate
        for candidate in candidates
        if isinstance(candidate, dict)
    ]

    if not valid_candidates:
        flash(
            "No valid candidate data was found for the report.",
            "warning",
        )
        return redirect(url_for("multiple_resume"))

    if not isinstance(job_skills, list):
        job_skills = []

    pdf_buffer = build_multiple_resume_pdf(
        valid_candidates,
        job_skills,
    )

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="multiple_resume_recruiter_report.pdf",
    )


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    debug_enabled = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_enabled)