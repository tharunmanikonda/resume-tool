# Rejection analysis — October 24, 2026

## Main finding

Tailoring is happening, but keyword alignment is not the same as demonstrated fit. The unresolved findings are a missed required response, internship eligibility mismatch, specialized requirements without clear supporting evidence, and historical titles/stacks that need reconciliation. These are actionable defects or plausible contributors; they are not confirmed explanations for every employer's decision. The user has clarified that the email error was limited to five files and is already fixed. Numerical evidence in 80% of bullets is an intentional XYZ-formula choice, not itself a defect or an established cause of rejection.

The strongest engineering narrative in the supplied base resume is full-stack/backend development with applied AI, retrieval, integrations, and production delivery. That is a starting point to verify, not independently verified employment history.

## Scope and limits

- Read 33 Gmail messages found through rejection-language searches after July 1, 2026 and a targeted SkyWest search. They include 25 rejection messages, one withdrawal, four application acknowledgments, and three additional SkyWest messages. This is a selected sample, not an exhaustive mailbox census or a rejection rate.
- Matched employer/role names to local saved job descriptions and resume drafts; reviewed eight saved PDFs through text extraction and three rendered pages for layout.
- Local sources: `config/resume_tool.db` opened read-only; `config/application_tracker.json`; `config/base_resume.json`; `config/user_profile.json`; `app.py`; the archive under `/Users/tharun/Documents/tharun-resume`.
- A saved file or generated draft is not proof that the same version was submitted. Submission receipts do not identify the attached file version. Generation timestamps are not application dates.
- Generic rejection language does not establish ATS failure, sponsorship screening, an assessment failure, recruiter skepticism, or a stronger competing applicant. Those remain unknown unless specifically stated.
- The current generator instructions explain a present design risk; this review does not establish which exact prompt version generated each historical resume.

## Findings in priority order

### 1. Contact information — resolved, limited historical issue

**User clarification:** The email issue affected only these five files and has already been fixed; the remaining resumes were correct. The table below preserves the historical observation, not a current remediation request. This issue should not be generalized to the wider rejection pattern.

Five of eight PDFs list **tmainkon.1@gmail.com**. The connected mailbox receiving the application messages is **tmanikon.1@gmail.com**. The differing letters are in the username, not just a display name.

| Saved PDF | Email shown |
|---|---|
| FirstDay Foundation — Senior Workday Developer | tmainkon.1@gmail.com |
| OnPay — GTM Systems Engineer | tmainkon.1@gmail.com |
| C.H. Robinson — Software Engineer Intern | tmainkon.1@gmail.com |
| Ferguson — Senior ERP Software Engineer | tmainkon.1@gmail.com |
| University Health KC — Application Developer | tmainkon.1@gmail.com |
| Ovative Group — Senior Full Stack Engineer | tmanikon.1@gmail.com |
| HAI Group — Software Development Intern | tmanikon.1@gmail.com |
| Wing — Software Engineer Intern | tmanikon.1@gmail.com |

The historical error could have affected direct recruiter contact for those files, but no particular rejection has been attributed to it. Phone numbers also differ between historical files; differences alone do not establish an error.

### 2. SkyWest is an explicit process withdrawal

[SkyWest withdrawal](https://mail.google.com/mail/u/0/#all/1a15bd08d62f4e5d): the employer says it contacted the applicant to move forward, did not receive a response, and withdrew the application. The preceding messages clarify what was requested: a brief survey, not a confirmed interview invitation.

- [Survey request](https://mail.google.com/mail/u/0/#all/1a133aff3e20143c) specified an October 19 deadline.
- [Reminder](https://mail.google.com/mail/u/0/#all/1a14c5d862b6b201) repeated the deadline and warned of withdrawal.
- The withdrawal says to contact the company if still interested.

**Action:** Check whether the survey was actually submitted and whether a receipt exists. If it was, use that evidence to request correction; otherwise ask whether the application can be reopened. No email was sent during this analysis.

### 3. Some applications have eligibility or specialist-depth gaps that wording cannot fix

| Employer/role | Evidence in saved JD and resume | Assessment and next action |
|---|---|---|
| C.H. Robinson — Software Engineering Internship 2027 | JD requires actively pursuing an undergraduate CS or related degree. Resume says current DBA study; its education section lists completed bachelor's/master's degrees. | Direct mismatch between stated requirement and visible education. Screen enrollment level before tailoring; do not label the profile “student-eligible” without checking the actual rule. |
| FirstDay Foundation — Senior Workday Developer | JD asks for 6+ years of hands-on Workday experience across several modules, onsite San Antonio work, and no sponsorship. Resume turns the two recent positions into Workday Integration Engineer/Developer; base resume does not document Workday. | Specialist experience is unverified. Even both recent roles combined do not demonstrate six years of Workday work. The rejection email's sender is nphosting.org and names the same role, so the employer association is probable, not independently confirmed. |
| Ferguson — Senior ERP Software Engineer | JD requires extensive UniBasic/Pick experience, phantom processes, multivalue dictionaries/files/triggers. Summary claims UniBasic/Pick/Trilogie; visible recent work mainly describes AI, Python, APIs, Oracle and “UniQuery-like” queries. | Analogous SQL/API work does not demonstrate extensive Pick development. Verify actual production UniBasic work or deprioritize this specialist lane. |
| University Health KC — Application Developer, ServiceNow | Posting/requisition title includes ServiceNow, but the detailed minimum requirements explicitly name ASP.NET, C#, VB.NET, SQL and JavaScript. The saved resume addresses much of that stack. | Substantial alignment to the detailed requirements. ServiceNow is a title/body inconsistency to clarify, not an established disqualifying gap. |
| OnPay — GTM Systems Engineer | JD calls for substantial HubSpot ownership: custom objects, workflows, lifecycle architecture, lead qualification/routing, and sales/marketing outcomes. Resume lists HubSpot and automation platforms, but recent bullets center on AI retrieval and transaction tooling; one uses “Zapier-style automation.” | Transferable integration experience is visible, but direct HubSpot ownership is weakly evidenced. Show a verified CRM implementation with operational outcomes, or choose an adjacent integration role. |
| Amazon Ring — CS Salesforce Developer | JD calls for 3+ years professional Salesforce development, Apex/LWC, Service Cloud, Voice, Data Cloud and platform governance. Tailored resume claims these across recent jobs; base resume does not document that stack. | Verify Salesforce history and duration. Email proves an assessment and recruiter call occurred, so this was not simply an initial resume rejection. It does not disclose why the final decision was made. |
| Audax — Salesforce Developer | Saved JD requires Apex/LWC/integrations and explicitly disallows current or future employer sponsorship. | Salesforce depth and authorization need verification. Generic rejection supplies no reason. |
| Antech — Technical Support Specialist | JD emphasizes software/hardware troubleshooting, customer tickets, remote desktop, PACS/DICOM. Resume adds PACS/DICOM and ServiceNow work absent from the base resume while much of its story remains software delivery. | Verify domain/support experience; distinguish building software from handling user support and imaging incidents. |
| Gowan — IT Network Technician | JD emphasizes LAN/WAN, Microsoft 365, endpoint management, AD, and onsite Yuma work. Resume adds substantial infrastructure/endpoint responsibilities to a software background. | Verify hands-on administration and location availability; software familiarity alone is insufficient proof. |

These are evidence gaps relative to the available base record, not an accusation that the experience is false. A base resume may omit real work. Confirm it before retaining specialist claims.

### 4. The generator can turn tailoring into changes to the factual story

The user intentionally uses numerical evidence in at least 80% of bullets to follow the XYZ formula. That stylistic choice is not evidence of weak quality or a cause of rejection, and this analysis does not recommend removing it. XYZ can clearly communicate accomplishment, measurement, and action.

Separately, current [experience-generation instructions](/Users/tharun/resume-tool/app.py:3037) request rounded estimates when work metrics are not stored in the profile. The question is the source of each number, not the proportion of quantified bullets: candidate-supplied measurements or defensible estimates can support an XYZ bullet; a model-created estimate does not become supported merely because it sounds plausible. This review has not established which individual metrics are verified, nor whether an employer rejected an application over them.

The [historical-title rules](/Users/tharun/resume-tool/app.py:3021) both forbid imitating the target family and permit JD-aligned retitling when the generated bullets support it. This permits circular justification: rewritten bullets can be used to validate a rewritten title.

The same McKinsey dates appear under Senior Full Stack Engineer, Workday Integration Engineer, Salesforce Developer, Support Engineer, and DevOps Engineer in the reviewed drafts. Uber changes similarly. The Advocates draft names Linq for the current employment period while the default profile names McKinsey; this may be an intentional alternate identity/employment arrangement, but it must be reconciled before treating versions as interchangeable.

**Why it matters:** an individual resume can overstate specialist depth or sound generic despite excellent keyword coverage. Across applications, interviews, and public profiles, changing factual history can create inconsistencies. This review does not establish that recruiters saw other versions or compared them.

**Action:** Lock employers, dates, employment relationships, historical titles, actual tools used, and validated metrics. Let tailoring select and reorder supported evidence. An unsupported requirement should remain a visible gap. Require candidate confirmation for any new factual claim, not just a second AI review of generated text.

### 5. Presentation and application settings can work against the intended fit

- All eight PDFs yielded readable text. This does not test any employer's ATS, but it provides no basis to blame unreadable PDFs as the common cause.
- Ovative's first page is dense and ends mid-experience; the file is two pages with several unrelated projects. A concise, role-relevant story would be easier to scan. Two pages alone is not a defect.
- Wing's second page contains only the AWS certification. This is a clear pagination problem; keep the certification on page one or omit it when irrelevant.
- C.H. Robinson's resume calls itself student-eligible while the displayed evidence does not meet the stated undergraduate condition. Its saved PDF also omits the current DBA from the formal education section despite mentioning it in the summary.
- The application profile defaults to $150,000–$180,000, while saved postings include The Advocates at $90,000–$100,000 and Ovative at $90,000–$132,000 base. This is only a risk if that default was actually submitted; no historical application-answer record was found here proving it was.
- The profile stores sponsorshipRequired=No and workAuthorization=Yes. This does not independently verify current or future sponsorship needs. Ovative, FirstDay, Audax and Allegion contain sponsorship restrictions. Confirm the underlying facts; do not infer status from graduate enrollment.

## Email outcome register

Every “rejected” entry below means a rejection was communicated, not that a particular cause was established. Dates below reflect the source message's UTC calendar date; Chicago dates can differ near midnight.

| Employer | Role | Outcome | Email |
|---|---|---|---|
| Ovative | Sr. Full Stack Engineer | Rejected; generic competitive-search wording | [Read](https://mail.google.com/mail/u/0/#all/1a16a8dd92ee4d2f) |
| HAI Group | Software Development Intern | Rejected; full saved JD not located in draft database | [Read](https://mail.google.com/mail/u/0/#all/1a16a2277901fa72) |
| OnPay | GTM Systems Engineer | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a15f22d933e41ee) |
| The Advocates | Systems & Integration Engineer | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a15f15d12a399a5) |
| SkyWest | Full-Stack Developer | Withdrawn for missing response/survey | [Read](https://mail.google.com/mail/u/0/#all/1a15bd08d62f4e5d) |
| Wing | Software Engineering Intern, Summer 2027 | Rejected; full saved JD not located in draft database | [Read](https://mail.google.com/mail/u/0/#all/1a15a4f56c73c164) |
| Antech | Technical Support Specialist | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a1401c71b8cc881) |
| icotec | IT Support and Platform Specialist | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a1399feb767f63c) |
| Gowan | IT Network Technician | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a1389167f637536) |
| Amazon Ring | CS Salesforce Developer | Rejected after assessment/recruiter call; reason unknown | [Read](https://mail.google.com/mail/u/0/#all/1a132b276ff1440b) |
| TreeHouse Foods | Application Developer | Rejected; saved JD permits general development and does not require deep Quickbase experience | [Read](https://mail.google.com/mail/u/0/#all/1a1244a826c9e687) |
| BankPlus | Automation Engineer | Rejected; reasonable apparent overlap, cause unknown | [Read](https://mail.google.com/mail/u/0/#all/1a121094c06797f3) |
| Southern Company | Application Developer I, Integrations | Rejected; cause unknown | [Read](https://mail.google.com/mail/u/0/#all/1a0f5c8b1b3406db) |
| Ferguson | Senior ERP Software Engineer | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a0c43975d131a0b) |
| University Health | Application Developer, ServiceNow | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a0b8bb5d7711ca5) |
| Wordware/Sauna | Growth Engineer, matched from saved draft | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a0a2f85dca89d12) |
| ASG | GTM Engineer | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a09f652b82e9ed8) |
| Allegion | Software Engineering/DevOps Intern | Rejected; enrollment and authorization conditions apply | [Read](https://mail.google.com/mail/u/0/#all/1a099b603d3371f8) |
| Toyota Automated Logistics | Software Developer Co-op | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a09171f2858c2e2) |
| Rothera | Senior Associate Software Engineer, Frontend | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a08d7ecdc4f0e9c) |
| C.H. Robinson | Software Engineering Internship 2027 | Rejected; undergraduate requirement mismatches resume | [Read](https://mail.google.com/mail/u/0/#all/1a089e2b6f22177e) |
| FirstDay association probable | Senior Workday Developer | Rejected; employer association needs confirmation | [Read](https://mail.google.com/mail/u/0/#all/1a0899060c094d33) |
| AllianceBernstein | Software Engineer | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a015e6f76045b79) |
| American Airlines | Engineer/Sr Engineer, IT Software, 87484 | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a0139095445a4de) |
| Finnegan | IT Support Specialist | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a135a869022b334) |
| Audax | Salesforce Developer | Rejected | [Read](https://mail.google.com/mail/u/0/#all/1a1035ca1f6d00b0) |

Movement Mortgage, Objective Partners, Objective Paradigm, and SWBC messages in the search sample were acknowledgments, not rejection decisions. Search keywords alone would have misclassified them.

## Practical changes and how to evaluate them

1. **Improve response handling.** The five-file email issue is already fixed. Check survey/assessment deadlines daily and keep a receipt or completion status for every required step.
2. **Build a verified evidence inventory.** For each job/project record the real title, employer/client relationship, dates, technologies actually used, system built, personal contribution, and metrics with their basis. Treat every unconfirmed detail as unverified.
3. **Check eligibility before generating a resume.** Record enrollment level/discipline, location and onsite schedule, authorization, current/future sponsorship, specialist years, and compensation range. Mark each as met, not met, or unknown; a high textual score must not erase a failed mandatory condition.
4. **Concentrate the next batch on verified fit.** Start with backend/full-stack, applied-AI application, and API/integration roles supported by actual work. Only pursue Workday, Salesforce, UniBasic, network administration, or medical-imaging support when the relevant experience is confirmed. A transferable skill is useful but does not establish vendor specialization.
5. **Tailor evidence rather than history.** Preserve factual identity and titles; choose the three most important requirements, then show one specific verified accomplishment for each. Avoid padding every role with the complete target stack. Retain only projects that strengthen this application.
6. **Measure the actual stages.** For each submitted application save the requisition ID, JD, exact submitted PDF/version, eligibility answers, submission date, required tasks, recruiter response, screen, assessment, interview, and final outcome. Current records mix generated/ready states with outcomes; neither 689 drafts nor 1,470 archive entries is an application denominator.
7. **Use a small prospective batch.** Review results from the next 20–30 verified-fit applications, separately tracking initial recruiter responses, completed required tasks, and later-stage advancement. This can identify where the process is failing; a small batch cannot establish a causal uplift or justify a precise hiring-probability score.

No application status, existing resume, generator code, or mailbox item was changed during this review.

## Reproducible evidence files

- [Follow-up review of 180 bullets across nine rejected resumes](/Users/tharun/resume-tool/docs/rejected-resume-bullet-review-2026-10-24.md) — sentence-level examples, requirement mapping and edits that preserve XYZ.

- [Email excerpts and message IDs](/Users/tharun/resume-tool/tmp/rejection-analysis/email-evidence.json)
- [Matched local records, including raw saved JDs and generated resumes](/Users/tharun/resume-tool/tmp/rejection-analysis/matched-local-records.json) — includes fuzzy-search candidates; not every returned row is a confirmed match.
- [Eight PDF text extracts and original file paths](/Users/tharun/resume-tool/tmp/rejection-analysis/pdf-extracts.json)
- Rendered pages: [Ovative](/Users/tharun/resume-tool/tmp/rejection-analysis/ovative.png), [C.H. Robinson](/Users/tharun/resume-tool/tmp/rejection-analysis/robinson.png), [Wing page 2](/Users/tharun/resume-tool/tmp/rejection-analysis/wing-page2.png).
