# AI Resume Screener — Database Design

## Existing baseline
- Flask, Flask-Login and Flask-SQLAlchemy.
- PostgreSQL configuration with SQLite fallback.
- Existing users, analyses, scoring preferences,
  analysis context and resume rewrites.

## Platform roles
- Candidate
- Recruiter
- Administrator

Company owner is a company-membership permission.

## New tables
- CandidateProfile
- RecruiterProfile
- Company
- CompanyMembership
- Job
- ResumeDocument
- Application
- ApplicationStatusHistory
- RecruiterNote
- Interview
- InterviewFeedback
- Notification
- AuditLog

## Existing table changes
- User: add role and account status.
- Analysis: add an optional application reference.
- Preserve existing users and standalone analyses.

## Main relationships
- A company has many jobs and recruiter memberships.
- A candidate owns resume documents.
- An application connects a candidate, job and resume document.
- An application can have multiple analyses and interviews.
- Status history records application transitions.

## Integrity rules
- Unique normalized user email.
- One candidate/recruiter profile per user.
- Unique company-user membership.
- One application per candidate per job.
- Scoring weights are nonnegative and total 100%.
- Interview end time follows start time.
- Store timestamps in UTC.
- Preserve the resume version submitted with each application.
- Store job requirements, weights and scoring-method version
  with each analysis.

## Access rules
- Candidates access their own records.
- Recruiter access requires authorized company membership.
- Recruiter notes and interview feedback are private.
- Admin privileges cannot be selected during registration.
- Scores support human hiring decisions.

## Migration plan
- Use migrations for schema changes.
- Preserve existing data.
- Assign existing ordinary users the candidate role.
- Keep application_id nullable for standalone analyses.
- Introduce changes incrementally and test them.