# ATS and human resume review: testing our generation theory

Research date: October 24, 2026. Focus: private-sector software and adjacent engineering applications.

## Verdict

Our theory is partly supported: relevant terminology helps discoverability, and clear, role-specific accomplishments help communicate fit. But the idea that keywords first “pass ATS” and good sentences then “pass humans” is too simple. Employer-configured eligibility rules, literal search, semantic matching and human judgment can overlap within application review. No public evidence reviewed establishes that our exact JD-to-generated-project workflow increases interview conversion.

We also do not know which stage rejected most of the user's applications. A rejection email is not evidence that keyword screening succeeded or that a human read the resume.

## What the primary sources establish

### 1. Parsing is separate from screening

Greenhouse documents that formatting problems can prevent extraction while leaving the resume attached for manual handling. A successful text extraction is therefore a usability check, not an advancement decision. In our earlier local review, extracting text from eight PDFs did not establish how any employer parsed or evaluated them. [Greenhouse: unsuccessful resume parse](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse).

### 2. Exact keywords matter in some searches

Greenhouse Talent Filtering supports exact keyword searches over resumes and notes. Required terms use AND logic; preferred terms use OR logic. Recruiters can also filter by location, education and other attributes. This supports including standard names for relevant skills and roles. It does not establish a universal keyword threshold or automatic progression once terms are present. [Greenhouse: Talent Filtering](https://support.greenhouse.io/hc/en-us/articles/27104809835291-Talent-Filtering).

### 3. Keyword coverage is not all that newer matching systems assess

Greenhouse Talent Matching compares resumes with employer-selected, weighted criteria including skills, experience and titles. Related terms can map to the same skill, so additional matched terms do not necessarily improve the result. This feature prioritizes review and does not itself advance or reject applicants. It is distinct from literal Talent Filtering. [Greenhouse: Talent Matching FAQ](https://support.greenhouse.io/hc/en-us/articles/41131886674075-Talent-Matching-FAQ).

Ashby lets employers define specific resume criteria, evaluates each as met/not met/undecided, and provides reasoning. Its current documentation also supports sorting by the percentage of configured criteria met. This is a percentage of employer-defined criteria, not an industry-wide resume score. [Ashby: AI-Assisted Application Review](https://docs.ashbyhq.com/ai-assisted-application-review).

Workday's August 2026 HiredScore release documents an optional LLM-based Fit & Gap enhancement that evaluates individual qualifications and points to resume evidence. Enablement requires customer opt-in; older requisitions or customers can retain the previous behavior. A Workday application URL alone does not establish that an employer uses this feature. [Workday: HiredScore release notes](https://doc.workday.com/hiredscore/en-us/workday-hiredscore/hiredscore-release-notes/2026/august/wednesday--5th-august.html).

**Inference for our tool:** a workflow, object, contribution and relevant result make a requirement easier to evaluate than an isolated skill name. That helps explain why “routing” can be ambiguous when the employer specifically needs sales-lead routing. Vendor documentation demonstrates these evaluation capabilities, not the accuracy of every deployment.

### 4. Application answers can cause rejection independently of resume wording

Greenhouse Auto-reject rules use answers to custom application questions. Employers can set a rejection reason and send an automated email. A resume with excellent keywords and sentences cannot override an incompatible answer in that configured rule. This finding concerns that documented feature, not every possible automated rejection mechanism. [Greenhouse: Auto-reject](https://support.greenhouse.io/hc/en-us/articles/360000653472-Auto-reject).

### 5. A displayed match indicator is not an interview probability

Microsoft explains that its sourcing view can display a 0–5 match score, but the numerical indicator is hidden once the person applies. Its FAQ also states that strong/good recommendations do not guarantee outcomes. This illustrates why sourcing, matching and application decisions must be distinguished. [Microsoft Careers: Transparency FAQ](https://careers.microsoft.com/v2/global/en/transparency.html).

Our own match score can be a diagnostic rubric. It should not be labeled proof of passing an employer's ATS or a calibrated probability of human review.

### 6. Recruiters explicitly value relevant actions and outcomes

Amazon's recruiters recommend straightforward, readable wording, quantified results where possible, accomplishments rather than duties, and prioritization around the role's basic/preferred qualifications. This supports our move away from generic project delivery statements. It does not mean every bullet needs a number or that a specific phrasing guarantees advancement. [Amazon: resume-writing tips](https://www.aboutamazon.com/news/workplace/amazon-job-application-resume-writing-tips).

Google's veteran resume guide recommends XYZ, meaningful measurement, individual contributions and context for interpreting impact. It supports the user's decision to use quantified accomplishments. The guide does not establish an 80% numerical threshold or mandate a tools/constraint/result clause in every sentence. [Google: resume-writing guide](https://services.google.com/fh/files/misc/resume-writing-tips-for-veterans-2021.pdf).

### 7. Better writing has causal evidence behind it, within a specific setting

Wiles, Munyikwa and Horton studied non-generative writing assistance on an online labor market. The paper reports that treated jobseekers were hired 8% more often and finds no evidence of reduced employer satisfaction. This is a relative effect, not eight percentage points. It supports clarity and correction, not a claim that generated project histories or the XYZ formula caused the increase. The setting is online contract work, limiting direct extrapolation to salaried engineering recruitment. [Authors' paper](https://www.emmawiles.com/storage/Algo_Writing_Assistance.pdf).

### 8. Good presentation still competes with other applicants

Ashby's April 2026 report analyzes over 109 million applications and 247,000 jobs through March 2026. It reports elevated applications per hire, averaging 291 in its current observation. This is vendor-customer observational data, not a representative count for every employer or a personal success probability. It nevertheless gives context: adequate fit does not guarantee limited interview slots. [Ashby: recruiter productivity](https://www.ashbyhq.com/talent-trends-report/reports/2023-recruiter-productivity-trends-report).

## Assessment of our specific hypotheses

| Hypothesis | Assessment | Consequence |
|---|---|---|
| Relevant keywords help | Supported for search and filtering | Include accurate standard terminology naturally. |
| Keyword overlap proves we pass ATS | Unsupported | Record screening as unknown unless actual advancement is observed. |
| Only humans assess sentence meaning | Contradicted by documented semantic-review features | Meaning and explicit requirement evidence can matter before and during human review. |
| Clear relevant accomplishments help humans assess fit | Supported by employer guidance and writing-assistance research | Make the system, personal contribution and outcome understandable. |
| XYZ is a useful writing framework | Supported as employer guidance | Keep it; do not confuse formula compliance with evidential strength. |
| 80% quantified bullets is an ATS rule | Not established | Keep it as the user's writing preference, not a claimed screening requirement. |
| JD characteristics can guide a coherent project narrative | Reasonable design hypothesis | Evaluate whether the resulting narrative actually demonstrates the requirements. |
| Creating a project story from the JD has been proven to improve hiring | Not established | Treat generated details as drafting proposals needing confirmation, not research-validated facts. |
| Better wording fixes eligibility, duration, compensation or location mismatches | Unsupported | Evaluate those conditions separately. |
| A generic rejection means a human disliked the sentences | Not established | Preserve uncertainty about the decision-maker and reason. |

## What this means for the intended generator

The user's intended creative sequence is understood as:

JD → required project characteristics → draft work-experience bullets → coherent project narrative → individual XYZ bullets.

The research supports using the JD to determine what the narrative must communicate. It does not validate generating unconfirmed employment facts. A JD can tell the tool what a convincing relevant contribution would look like; it cannot establish that the applicant made that contribution. Software typically assesses claims in the submitted material; that is not independent verification that the work happened.

The generator should distinguish four separate questions:

1. **Can the application be read and found?** Text extraction, clear sections, standard relevant names, complete fields.
2. **Does it meet the employer's criteria?** Required capability, specialist depth, duration and application conditions; mark direct, transferable, missing or unknown.
3. **Does the writing demonstrate the capability?** Concrete project/workflow, personal action, implementation mechanism and a result tied to that action.
4. **Can the applicant support the claims?** Tools used, actual responsibility, project context, metric basis and a consistent employment history.

A single aggregate score should not erase a failed mandatory condition or hide an unsupported central claim. The tool can expose these checks separately without pretending to reproduce a private employer's configuration.

## A concrete example from our review

The OnPay resume says it built routing/webhook workflows and improved routing accuracy. That supplies technical terminology and a number. It leaves the routed object unnamed, so it does not clearly establish lead routing or CRM lifecycle ownership.

For review, ask: What was routed? From which system to which destination? Which rules were implemented? What did the candidate personally build? What does accuracy mean here?

Those questions are useful for both a human reader and a criterion-based software assessment. If the work concerned transactions, retain that fact and describe its transferable value. Do not silently turn transactions into sales leads just to close a textual gap.

Likewise, BankPlus's reconciliation example already names a business process, operations users and a measurable reduction in manual work. It is stronger evidence for that job than a vague opening about AI delivery. AI need not be removed; its role should be described in relation to the employer's actual problem.

## How to test our redesign

### Before applications

- Compare current and revised drafts for the same set of JDs, holding the underlying facts constant.
- Have a reviewer evaluate each important requirement using only the resume text. Ask the reviewer to identify the exact supporting sentence and what remains unknown.
- Use a separate sentence check for an identifiable work object, personal contribution, technically coherent mechanism, defined outcome, grammar and unnecessary clauses.
- Keep keyword coverage, requirement evidence, factual support and readability as separate results.
- Treat model reviewers as fallible proxies, not access to an employer's ATS. A generated sentence must not be its own independent factual source.

### After applications

- Save the exact submitted resume, JD, application answers and date.
- Track recruiter outreach, completed screens, assessments, interviews and offers separately.
- Distinguish stage observed from stage assumed. A generic rejection remains reason unknown.
- If comparing approaches, assign each eligible application to one version prospectively across reasonably comparable roles; never submit duplicate applications just to test wording.
- A small batch can reveal process defects and directional signals. It cannot establish a reliable causal improvement across different companies. Report sample size and uncertainty rather than a guaranteed uplift.

## Research limits

Primary vendor documentation establishes available behavior, not how frequently each feature is enabled. Employer guidance establishes stated preferences, not the causal weight of each sentence choice. The writing study tests a particular intervention and labor market. None of these sources provides access to the configurations, review activity or reasons for the user's individual rejections.

No generator code or application data was changed during this research.
