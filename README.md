# Resume Generator With Application Companion

Local resume generation, PDF export, application tracking, LinkedIn job capture, and ATS form autofill in one Flask and React application.

The browser extension is a companion to the local server. It does not contain a separate resume-generation backend and should always use the same running Flask application as the main UI.

## Capabilities

- Generate a resume tailored to the current job description.
- Keep separate persistent drafts for multiple LinkedIn jobs.
- Edit titles, summaries, technical skills, work history, and generated bullets before PDF creation.
- Select which saved work experiences appear in each draft.
- Generate and preview DOCX/PDF output.
- Track applications by company, role, date, source, and status.
- Generate conversational reachout messages and application-question answers.
- Find focused LinkedIn people and hiring-post searches.
- Detect and fill recognized application fields on supported ATS platforms.
- Attach the selected generated PDF to compatible resume upload fields.

The extension never submits an application, sends a LinkedIn message, clicks Apply, reads LinkedIn cookies, or crawls job listings.

## System Requirements

Required:

- macOS or Linux. The main development and extension flow is tested on macOS.
- Python 3.10 or newer. Python 3.11 is recommended.
- Node.js 20 or newer with npm.
- Chrome or Arc with Manifest V3 and Developer mode available.
- An OpenAI API key for resume, reachout, and follow-up generation.
- Network access to the OpenAI API during AI generation.

Required for PDF conversion:

- LibreOffice with the `soffice` executable available.
- macOS: `brew install --cask libreoffice`
- Ubuntu/Debian: `sudo apt-get install libreoffice`
- A custom executable can be configured with `SOFFICE_PATH` or `LIBREOFFICE_PATH`.

Optional:

- A PostgreSQL database through `DATABASE_URL`. SQLite is used by default.
- A local faster-whisper model through `FASTER_WHISPER_MODEL_PATH`. Otherwise `tiny.en` is used when transcription is requested.
- Playwright Chromium for the real-browser extension smoke test.

## Repository Setup

### Automated Setup

From the repository root:

```bash
./setup.sh
```

The script checks Python and Node, creates `.venv`, installs Python and npm dependencies, creates `.env` from `.env.example`, builds the web app and extension, and starts Flask.

### Manual Setup

Use this sequence when an AI agent or developer needs explicit control over each step:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm install
cp .env.example .env
npm run build
.venv/bin/python app.py
```

The application starts at [http://127.0.0.1:5001](http://127.0.0.1:5001) by default.

After the first setup, use:

```bash
./run_local.sh
```

`run_local.sh` rebuilds both frontends and starts the local server. It does not reinstall dependencies unless `node_modules` is missing.

## Environment Configuration

Edit `.env` before generating a resume:

```dotenv
OPENAI_API_KEY=your-api-key

# Optional overrides
OPENAI_ANALYSIS_MODEL=gpt-4o-mini
OPENAI_RESUME_MODEL=gpt-5-mini
OPENAI_ANALYSIS_TIMEOUT_SECONDS=120
OPENAI_RESUME_TIMEOUT_SECONDS=180
FLASK_PORT=5001
OUTPUT_ROOT=resumes
LOCAL_DATABASE_PATH=config/resume_tool.db
# DATABASE_URL=postgresql+psycopg://user:password@localhost/resume_tool
# SOFFICE_PATH=/absolute/path/to/soffice
# RESUME_TEMPLATE_PATH=/absolute/path/to/template.docx
# FASTER_WHISPER_MODEL_PATH=/absolute/path/to/model
```

`OPENAI_API_KEY` is required for AI generation. The rest have working local defaults.

## First-Run Profile

Personal resume data is not committed to Git.

- `config/user_profile.template.json` is the committed blank schema.
- `config/user_profile.json` is the ignored permanent profile.
- `config/session_profile.json` is an ignored temporary override that resets when the server restarts.
- `config/settings.json` stores application settings such as the output directory and contact identities.

When `config/user_profile.json` is missing, the UI opens onboarding and blocks generation. Complete at least:

- Name, location, phone, and email.
- One enabled and complete work experience.
- One project.
- One certification.

An experience is usable only when it is enabled and its company, location, title, and dates are all filled.

Do not commit a real `config/user_profile.json` or `config/session_profile.json`. For a new user, let onboarding create the permanent file instead of putting personal data in the template.

## Running the Server

Default command:

```bash
./run_local.sh
```

Use another port when `5001` is occupied:

```bash
FLASK_PORT=5002 ./run_local.sh
```

The extension automatically checks `127.0.0.1:5001`, `127.0.0.1:5002`, and their `localhost` equivalents. For any other port, open the extension Options page and set the complete local server URL.

Useful readiness checks:

```bash
curl http://127.0.0.1:5001/health
curl http://127.0.0.1:5001/api/extension/status
```

The extension status response reports server, AI, PDF, profile, and queue readiness.

## Building the Frontends

Build the main React application and extension:

```bash
npm run build
```

Build only the main application:

```bash
npm run build:app
```

Build only the extension:

```bash
npm run build:extension
```

Build output:

- Main web application: `static/react`
- Browser extension: `extension/dist`

Always load `extension/dist` in the browser. Do not load `extension/` or `extension/public` directly.

## Installing the Browser Extension

1. Start the Flask app and confirm `/api/extension/status` returns success.
2. Run `npm run build:extension`.
3. Open `chrome://extensions` in Chrome or `arc://extensions` in Arc.
4. Enable **Developer mode**.
5. Select **Load unpacked**.
6. Select the repository's `extension/dist` directory.
7. Approve the requested LinkedIn, ATS, and localhost host permissions.
8. Pin the extension if a persistent toolbar action is useful.
9. Refresh any LinkedIn or ATS tabs that were already open.
10. Click the extension icon or the page-edge **Resume** button.

After rebuilding the extension, return to the browser extension page and press **Reload** for the unpacked extension. Rebuilding files alone does not update an already loaded extension runtime.

Disable the older standalone Job AutoFill extension when using this merged extension. Running both can create duplicate observers and competing field updates.

## Extension Workspaces

### Resume

Resume is always the default workspace.

On a LinkedIn Jobs page it reads only the currently displayed job and extracts:

- LinkedIn job ID and canonical URL.
- Company, role, and location.
- Full job description.
- Available posting metadata.

Use **Refresh** when LinkedIn has finished loading but the company, role, or description is missing. Refresh forces a new page extraction and waits for the updated context before rendering it.

Generating a resume creates a persistent draft in the local database. Moving to another LinkedIn job does not overwrite an existing draft. The recent draft tray can reopen generation progress, editing, PDF, messages, or search tools.

### Autofill

Autofill never opens automatically. Select it manually while viewing an application page.

It provides:

- ATS and application-page detection.
- Recognized, filled, unmatched, sensitive, and file-field counts.
- Manual **Fill this page** behavior.
- Optional automatic filling for newly rendered form steps.
- Contact identity selection.
- Permanent and session-only application-profile editing.
- JSON import and export for application details.
- Saved custom answers using `Question text => Answer` lines.
- Selection from current, non-stale PDFs generated within the last 24 hours.
- Generated resume PDF attachment.
- Detection of unanswered written application questions across supported ATS frames.
- User-triggered AI answer drafting grounded in the selected PDF and its job description, with inline copy and regenerate actions.

AI answers are never inserted or submitted automatically. Sensitive questions involving authorization, sponsorship, salary, availability, legal declarations, security clearance, or demographic information are marked for manual confirmation and are not sent to the model.

Existing field values are preserved. The extension does not click Next or Submit. The user remains responsible for reviewing every answer and submitting the application.

## Supported ATS Platforms

The manifest and runtime include detection for:

- Greenhouse
- Lever
- Workday and MyWorkdayJobs
- LinkedIn Easy Apply
- Ashby
- iCIMS
- Oracle Recruiting and Taleo
- SmartRecruiters
- Jobvite
- Avature
- SAP SuccessFactors
- Phenom
- Google Careers

The runtime handles native inputs, textareas, selects, radio groups, checkboxes, controlled input events, open shadow roots, same-tab frames, and dynamically rendered multi-step forms.

Support does not mean every employer customization is guaranteed. Closed shadow roots, browser-protected controls, CAPTCHA, unusual cross-origin widgets, or custom upload components can require manual input. Some ATS platforms reject programmatically assigned files; use the normal file picker and select the generated PDF from the configured output directory in that case.

## Resume and Tracker Workflow

1. Open a LinkedIn job.
2. Open the extension; Resume is selected by default.
3. Review the extracted company, role, and job description.
4. Use Refresh if extraction is incomplete.
5. Select a contact identity and enabled work experiences.
6. Generate the resume and resolve duplicate-application decisions if shown.
7. Review and edit the generated content.
8. Generate the latest PDF.
9. Open the employer application page.
10. Select Autofill, fill recognized fields, and attach the generated resume.
11. Review the entire application and submit it manually.
12. Return to the draft and explicitly mark it Applied.

Filling a form does not mark an application as Applied. Tracker state changes only after explicit confirmation.

## Persistence

- Resume drafts and generation tasks: SQLite at `config/resume_tool.db` by default.
- PostgreSQL: supported through `DATABASE_URL`.
- Tracker records: `config/application_tracker.json`.
- Permanent personal profile: ignored `config/user_profile.json`.
- Session profile: ignored `config/session_profile.json`.
- Output directory and identities: `config/settings.json`.
- Generated resumes: the output directory selected in Settings.

Database tables are created automatically at startup. Alembic migrations are also available:

```bash
PYTHONPATH=. .venv/bin/alembic upgrade head
```

## Verification

Run Python tests:

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

Run JavaScript syntax and production builds:

```bash
node --check extension/public/service-worker.js
node --check extension/public/autofill-config.js
node --check extension/public/autofill-matcher.js
node --check extension/public/autofill-content.js
npm run build
```

Install Playwright Chromium and run the extension smoke test while the local server is running:

```bash
npx playwright install chromium
node tests/extension_autofill_smoke.mjs
```

For a non-default server:

```bash
RESUME_SERVER_URL=http://127.0.0.1:5002 node tests/extension_autofill_smoke.mjs
```

The smoke test loads the unpacked extension in Chromium, verifies Resume is the default workspace, fills a Greenhouse-style form, confirms controlled-input events, rescans a second form step, and attaches a generated PDF. It requires at least one non-stale PDF-ready draft for the attachment assertion.

## AI Agent Installation Checklist

An AI agent setting up this repository should follow this order:

1. Read this README and inspect `.env.example`, `requirements.txt`, and `package.json`.
2. Confirm `python3`, `node`, `npm`, and LibreOffice are available.
3. Create `.venv`; do not create a differently named environment if using the provided scripts.
4. Install Python and npm dependencies.
5. Create `.env` without exposing or committing API keys.
6. Run `npm run build` before loading the extension.
7. Start Flask and verify `/health` and `/api/extension/status`.
8. Do not fabricate or commit personal profile data. Use onboarding or an ignored local profile.
9. Load only `extension/dist` as the unpacked extension.
10. Reload the extension and refresh existing browser tabs after code changes.
11. Run the Python tests and extension build before reporting completion.
12. Never validate autofill by submitting a real job application.

## Troubleshooting

### Extension opens but says the server is offline

- Confirm the Flask server is running.
- Check `/api/extension/status` in the browser.
- Open the extension Options page and verify the URL and port.
- Do not use `0.0.0.0` as the extension server URL; use `http://127.0.0.1:<port>`.

### Extension changes are not visible

- Run `npm run build:extension`.
- Open the browser extension page and press Reload.
- Refresh the LinkedIn or ATS page to replace old content scripts.

### LinkedIn details are empty or stale

- Wait for the selected job detail pane to finish loading.
- Press Refresh in the Resume workspace.
- Confirm the active page is under `https://www.linkedin.com/jobs/`.

### Autofill detects no fields

- Confirm the application form is visible, not only the job description.
- Press Refresh in Autofill after moving to a new form step.
- Inspect the unmatched-field list.
- Check that the host is included in `extension/public/manifest.json`.
- Reload the extension after manifest changes.

### Resume attachment fails

- Generate a current PDF and ensure the draft says PDF Ready.
- Regenerate the PDF after any resume edit.
- Confirm the ATS exposes a resume file input.
- Use the ATS file picker manually if it blocks programmatic attachment.

### PDF conversion is unavailable

- Install LibreOffice.
- Confirm `soffice --version` works, or configure `SOFFICE_PATH`.
- Restart the Flask server after changing the executable path.
- Check `/health` for the PDF conversion status.

### Port is already in use

```bash
FLASK_PORT=5002 ./run_local.sh
```

Then update the extension Options page if automatic discovery does not select that server.

### Tests cannot import local modules

Run pytest with the repository root on `PYTHONPATH`:

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

## Architecture Map

```text
app.py                                  Flask APIs, profile, resume pipeline, PDF and tracker routes
database.py                             SQLAlchemy configuration and draft/task models
extension_drafts.py                     Persistent draft store and queue behavior
config/user_profile.template.json       Blank committed personal/application profile schema
extension/src/panel-main.jsx            Resume and Autofill drawer UI
extension/public/service-worker.js      Local API bridge, tab/frame routing and PDF transfer
extension/public/content-script.js      LinkedIn job extraction and LinkedIn drawer host
extension/public/panel-host.js           Drawer host on non-LinkedIn pages
extension/public/autofill-config.js      ATS hosts, field patterns and dropdown mappings
extension/public/autofill-matcher.js     Deep field discovery and profile matching
extension/public/autofill-content.js     Field filling, events, rescans and file attachment
extension/dist                          Production unpacked extension output
tests/test_autofill_integration.py       Backend/profile/manifest safety tests
tests/extension_autofill_smoke.mjs       Real Chromium extension workflow test
```

## Security and Privacy

- The Flask server binds to `127.0.0.1` by default.
- Personal profile and session files are ignored by Git.
- API keys belong only in `.env` or the process environment.
- The extension requests host access only for LinkedIn, supported ATS domains, and the local server.
- The extension reads the active supported page; it does not crawl other jobs or access LinkedIn cookies.
- Recognized Autofill fields and saved custom answers come from the local profile. AI-written application answers run only after **Ask AI** is clicked and use the selected current PDF and its JD.
- The application-answer workflow blocks legal, visa, demographic, salary, authorization, and other sensitive questions instead of inventing answers.
- Review generated resumes, autofilled fields, and uploaded files before submitting anything.

## License

MIT
