import json
import os
import re

from io import BytesIO
from xml.sax.saxutils import escape

import pdfplumber
from docx import Document
from flask import Flask, render_template, request, send_file
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
from werkzeug.utils import secure_filename


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

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


@app.route("/")
def home():
    """
    Display the homepage.
    """

    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_resume():
    """
    Upload, analyze and delete the temporary resume.
    """

    if "resume" not in request.files:
        return render_template(
            "index.html",
            upload_error="No resume file was received.",
        )

    file = request.files["resume"]

    job_description = request.form.get(
        "job_description",
        "",
    ).strip()

    if file.filename == "":
        return render_template(
            "index.html",
            upload_error="Please select a resume file.",
        )

    if not job_description:
        return render_template(
            "index.html",
            upload_error="Please paste the job description.",
        )

    if not allowed_file(file.filename):
        return render_template(
            "index.html",
            upload_error="Only PDF and DOCX files are allowed.",
        )

    filename = secure_filename(file.filename)

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename,
    )

    file.save(file_path)

    extension = filename.rsplit(".", 1)[1].lower()

    file_size_bytes = os.path.getsize(file_path)

    if file_size_bytes < 1024:
        formatted_file_size = f"{file_size_bytes} bytes"

    elif file_size_bytes < 1024 * 1024:
        formatted_file_size = (
            f"{file_size_bytes / 1024:.2f} KB"
        )

    else:
        formatted_file_size = (
            f"{file_size_bytes / (1024 * 1024):.2f} MB"
        )

    try:
        extracted_text = extract_resume_text(
            file_path,
            extension,
        )

    except Exception as error:
        app.logger.exception(
            "Resume text extraction failed: %s",
            error,
        )

        return render_template(
            "index.html",
            upload_error=(
                "The resume was uploaded, but its text "
                "could not be extracted."
            ),
        )

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    if not extracted_text.strip():
        return render_template(
            "index.html",
            upload_error=(
                "The resume was uploaded, but no readable text was found."
            ),
        )

    cleaned_resume_text = extracted_text.strip()

    resume_word_count = len(
        cleaned_resume_text.split()
    )

    resume_character_count = len(
        cleaned_resume_text
    )

    resume_line_count = len(
        [
            line
            for line in cleaned_resume_text.splitlines()
            if line.strip()
        ]
    )

    resume_info = {
        "filename": filename,
        "file_type": extension.upper(),
        "file_size": formatted_file_size,
        "word_count": resume_word_count,
        "character_count": resume_character_count,
        "line_count": resume_line_count,
        "status": "Successfully processed",
    }

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
        resume_skills,
    )

    ats_rating = calculate_ats_rating(
        resume_score
    )

    resume_strength = calculate_resume_strength(
        extracted_text,
        resume_skills,
        resume_score,
    )

    skill_gap_analysis = calculate_skill_gap_analysis(
        resume_skills,
        job_skills,
    )

    final_recommendation = generate_final_recommendation(
        resume_score,
        matching_skills,
        missing_skills,
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
        final_recommendation=final_recommendation,
        resume_info=resume_info,
    )


@app.route("/download-report", methods=["POST"])
def download_report():
    """
    Generate and download the PDF analysis report.
    """

    report_data = {
        "filename": request.form.get(
            "filename",
            "Resume",
        ),
        "file_type": request.form.get(
            "file_type",
            "Unknown",
        ),
        "file_size": request.form.get(
            "file_size",
            "Unknown",
        ),
        "word_count": request.form.get(
            "word_count",
            "0",
        ),
        "resume_score": request.form.get(
            "resume_score",
            "0",
        ),
        "ats_label": request.form.get(
            "ats_label",
            "Not available",
        ),
        "strength_score": request.form.get(
            "strength_score",
            "0",
        ),
        "strength_label": request.form.get(
            "strength_label",
            "Not available",
        ),
        "final_title": request.form.get(
            "final_title",
            "Resume Analysis",
        ),
        "final_message": request.form.get(
            "final_message",
            "",
        ),
        "next_action": request.form.get(
            "next_action",
            "",
        ),
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
    }

    pdf_buffer = build_analysis_pdf(
        report_data
    )

    original_name = os.path.splitext(
        report_data["filename"]
    )[0]

    safe_report_name = secure_filename(
        original_name
    )

    if not safe_report_name:
        safe_report_name = "resume"

    download_filename = (
        f"{safe_report_name}_analysis_report.pdf"
    )

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_filename,
    )


if __name__ == "__main__":
    app.run(debug=True)
