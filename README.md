AI Resume Screener

An intelligent, recruiter-focused web application that compares PDF and DOCX resumes with a job description, produces evidence-based scores, ranks multiple candidates, and generates personalized recommendations and interview questions.

Live Demo and Source Code

Live Demo: https://ai-resume-screener-0nwr.onrender.com

GitHub Repository: https://github.com/venkycodesdev/AI-Resume-Screener

Overview

AI Resume Screener helps candidates evaluate their resumes and helps recruiters compare multiple applicants consistently. The application extracts resume content, detects relevant skills and evidence, evaluates four scoring categories, and calculates a weighted overall match score.

The project includes secure user authentication, saved analysis history, downloadable PDF reports, responsive interfaces, file validation, and a PostgreSQL production database.

Features

PDF and DOCX resume uploads

Pasted or uploaded job descriptions

File-type, file-size, empty-content, and corrupted-file validation

Single-resume analysis

Multiple-resume analysis and weighted candidate ranking

Candidate comparison table

Best-candidate highlighting

Candidate strengths and weaknesses

Hiring recommendations

Matching and missing skill detection

Four-category score breakdown

Weighted overall resume score

Targeted resume-improvement recommendations

Technical, resume-based, skill-gap, project, and role-based interview questions

Downloadable PDF analysis reports

Registration, login, logout, and user-data isolation

Saved analysis and resume history

Responsive desktop, tablet, and mobile design

PostgreSQL production storage with SQLite fallback for local development

Scoring System

The overall score uses four evidence-based categories:

Category

Weight

Skills Match

40%

Experience Relevance

30%

Projects Relevance

20%

Education Match

10%

Overall Score =
    (Skills x 0.40) +
    (Experience x 0.30) +
    (Projects x 0.20) +
    (Education x 0.10)

The category calculations use detected resume evidence and job-description relevance. The scoring logic is designed to avoid giving an easy or unsupported 100% score.

Recruiter Recommendations

Candidates are assigned a recommendation based on their weighted score and supporting evidence:

Strong Match

Potential Match

Needs Review

Low Match

The multiple-resume workflow ranks candidates using the weighted overall score instead of basic skill matching alone.

Technology Stack

Backend

Python

Flask

Flask-Login

Flask-SQLAlchemy

Gunicorn

PostgreSQL in production

SQLite for local fallback

Resume and Report Processing

pdfplumber

pdfminer.six

python-docx

ReportLab

Pillow

Frontend

HTML5

CSS3

JavaScript

Jinja2 templates

Deployment

Render Web Service

Render PostgreSQL

GitHub

Architecture

Browser
   |
   v
Flask routes and authentication
   |
   +--> File validation and secure text extraction
   |
   +--> Resume/JD scoring engine
   |       +--> Skills
   |       +--> Experience
   |       +--> Education
   |       +--> Projects
   |
   +--> Recommendations and interview questions
   |
   +--> PDF report generation
   |
   v
SQLAlchemy
   +--> PostgreSQL (production)
   +--> SQLite (local fallback)

Project Structure

AI-Resume-Screener/
|-- app.py
|-- requirements.txt
|-- README.md
|-- .gitignore
|-- static/
|   |-- css/
|   |   `-- style.css
|   `-- js/
|       `-- script.js
|-- templates/
|   |-- index.html
|   |-- multiple_resume.html
|   |-- history.html
|   |-- analysis_details.html
|   `-- other application templates
`-- uploads/
    `-- .gitkeep

Local Installation

1. Clone the repository

git clone https://github.com/venkycodesdev/AI-Resume-Screener.git
cd AI-Resume-Screener

2. Create a virtual environment

python -m venv venv

Windows PowerShell:

.\venv\Scripts\Activate.ps1

macOS/Linux:

source venv/bin/activate

3. Install dependencies

pip install -r requirements.txt

4. Configure environment variables

Create a local .env file or define these variables in your shell:

SECRET_KEY=replace-with-a-long-random-secret
FLASK_DEBUG=0

DATABASE_URL is optional for local development. Without it, the application uses its local SQLite fallback.

Never commit .env, credentials, database files, or uploaded resumes.

5. Run the application

python app.py

Open:

http://127.0.0.1:5000

Usage

Single-resume workflow

Register and log in.

Open the Single Resume page.

Upload a valid PDF or DOCX resume.

Paste or upload a job description.

Run the analysis.

Review the overall score, category scores, skills, recommendations, and interview questions.

Download the PDF report or open the saved analysis later from History.

Multiple-resume workflow

Open the Multiple Resume page.

Upload multiple PDF or DOCX resumes.

provide the job description.

Run the analysis.

Review the comparison table, candidate ranking, strengths, weaknesses, and hiring recommendation.

Security and Reliability

Environment-based production secrets

Production debug mode disabled

Password hashing and authenticated routes

User-owned history and analysis isolation

Safe filename handling

PDF/DOCX format validation

File-size limits

Empty and corrupted document handling

Friendly validation and server-error messages

Duplicate-submission prevention

PostgreSQL production persistence

Screenshots

Home Page



Single Resume Analysis



Candidate Comparison and Ranking



Resume History



Mobile Responsive Design



Testing

The final release was tested for:

Registration and login/logout

User-data isolation

Single- and multiple-resume workflows

Weighted scoring and candidate ranking

PDF report generation

Saved analysis history

Empty and very short resumes

Resumes with no detected skills

Job descriptions with few or no recognized skills

Duplicate, invalid, unsupported, oversized, and corrupted files

Desktop, tablet, and mobile responsiveness

Render deployment and PostgreSQL persistence

Future Improvements

Semantic matching with transformer embeddings

OCR support for scanned resumes

Configurable scoring weights for recruiters

Recruiter team workspaces and collaboration

Job and candidate search filters

Email notifications and interview scheduling

Multilingual resume analysis

Automated test suite and continuous integration

Author

Venkatesh
B.Tech - Artificial Intelligence and Machine Learning

GitHub: venkycodesdev

Live project: AI Resume Screener

Project Status

Final release preparation in progress. Built for educational, portfolio, and demonstration purposes.