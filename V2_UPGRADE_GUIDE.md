# AI Resume Screener V2 — Windows Upgrade Guide

## Safest method

1. Keep your current `AI-Resume-Screener` folder as a backup.
2. Extract the delivered ZIP.
3. Open the extracted `AI-Resume-Screener-V2` folder.
4. Copy all files and folders inside it.
5. Paste them into:

```text
C:\Users\karam\OneDrive\Desktop\AI-Resume-Screener
```

6. Select **Replace the files in the destination**.

Do not delete or replace your `.env` file. The delivered ZIP intentionally does not contain one.

## Install and test

Open PowerShell in your project folder:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m py_compile app.py v2_features.py
python -m pytest -q
python app.py
```

Expected automated-test result:

```text
6 passed
```

Open `http://127.0.0.1:5000` and test:

1. Log in.
2. Open **Dashboard → Scoring Weights** and save weights totaling 100%.
3. Analyze a resume and job description.
4. Confirm **Why You Received These Scores** appears.
5. Select **Improve My Resume**.
6. Generate, edit and save a rewrite.
7. Download DOCX and PDF.
8. Re-analyze the improved resume.
9. Open **Dashboard → Saved Reports** and test search, download and delete.
10. Analyze multiple resumes and test candidate search, filters and sorting.

Old history remains available. To rewrite an old resume, analyze that resume once again because Version 1 did not store its extracted text.

## GitHub and Render

```powershell
git switch -c version-2
git add .
git commit -m "Release AI Resume Screener Version 2"
git push -u origin version-2
```

Confirm GitHub Actions passes. Then merge `version-2` into `main`. Render should deploy the updated `main` branch automatically.

After Render reports **Deploy live**, repeat the ten production tests above on the live URL.
