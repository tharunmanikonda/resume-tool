# Rejected resume bullets: sentence quality and requirement alignment

## Conclusion

Several resumes genuinely match substantial portions of their job descriptions. The claim that all of them merely match keywords would be too strong. The main writing weakness is that the bullets often name a relevant system and tools without explaining the particular feature, decision, or workflow that makes the accomplishment persuasive for this employer.

The clearest examples of good alignment are Ovative, BankPlus, and The Advocates. OnPay and ASG have a larger gap between the GTM positioning in the summary/skills and the work described in the experience section. Rothera has relevant frontend evidence, but backend/AI bullets receive too much of the first-read attention. Ferguson includes direct UniBasic claims, yet the detail does not establish the depth required by the JD. University Health's detailed .NET requirements are substantially addressed despite an unresolved ServiceNow title/body inconsistency in the posting.

These are assessments of the saved writing and its fit to the saved JD. They do not establish the reason for an employer's rejection, validate the underlying accomplishments, or prove which file was submitted.

## What was examined

Read all 180 professional-experience bullets in nine stored resume drafts alongside their saved JDs: OnPay, The Advocates, BankPlus, Ovative, Ferguson, University Health KC, ASG, Rothera, and TreeHouse Foods. Bullet numbers below follow experience order across all employers within a resume. The [source extract](/Users/tharun/resume-tool/tmp/rejection-analysis/bullet-review-source.json) preserves every bullet, the raw JD, and the draft ID.

This review keeps the user's intentional XYZ approach. Quantified bullets are useful when X is a specific accomplishment, Y measures that accomplishment, and Z explains the action. The percentage of quantified bullets is not treated as a defect. The resolved five-file email issue is excluded from this evaluation.

## Requirement-by-requirement assessment

| Resume | Requirements the bullets do address | What is missing or weaker | Judgment |
|---|---|---|---|
| Ovative | ETL/data pipelines, relational databases, cloud, React, containers, CI/CD, testing, mentoring and cross-functional delivery | Specific product ownership, technical trade-offs and requirements documentation receive less concrete treatment. Digital marketing is preferred, not mandatory. | Substantial direct fit. Writing can be sharper; the resume is not broadly off-target. |
| BankPlus | Business-process automation, API integration, AI delivery, testing, monitoring, architecture and security-aware engineering | Recent opening bullets emphasize RAG and prototype speed. Requirements gathering, documentation and vendor engagement deserve clearer evidence; vendor-led engagement is an ideal, not an absolute requirement. | Substantial direct and transferable fit. The best business-automation example is buried under Uber. |
| The Advocates | Python/SQL, API work, retries, data quality, reconciliation, identity/SSO and runbooks | First three bullets sell AI retrieval rather than connected business systems. Account provisioning, recurring reporting and nontechnical user support are less explicit. Filevine is context, not stated as a mandatory prior skill. | Substantial transferable fit. Ordering and concrete business-system context are the main writing opportunities. |
| OnPay | Python/JavaScript/SQL, APIs, webhooks, integration reliability, routing and reconciliation | Experience does not clearly identify a CRM being owned, HubSpot custom objects, lifecycle stages, lead qualification, sales/marketing handoffs or speed-to-lead. “Routing” does not identify what is routed. | Partial fit. Strong general integration evidence; weak proof of the central CRM/GTM operating responsibility. |
| ASG | AI workflows, Python/TypeScript, APIs, data pipelines, one Clay GTM prototype | Production Clay ownership, enrichment waterfalls, CRM integration ownership, outbound-stack deployments and Bowtie-linked business reporting are not demonstrated clearly. Portfolio/segment experience is not established by generic enterprise delivery. | Partial fit. Prototype evidence is useful but narrower than operating the production systems requested. |
| Rothera | React/TypeScript, admin dashboards, large lists, accessibility, testing, internal operational tools | The strongest frontend examples appear after ingestion and caching bullets. Tables, filters, pagination and forms are mostly compressed into “CRUD.” | Substantial technical fit with misplaced emphasis and shallow feature detail. |
| TreeHouse Foods | Development/scripting, APIs, relational data, AI coding assistants, Agile, low-code integrations | Problem discovery with business users, independent product ownership and ongoing improvement of a specific business application are vague. | Substantial technical fit. A lifecycle story would be more convincing than a broad tool inventory. |
| University Health KC | C#/ASP.NET/SQL Server, database work, debugging, production support, security, testing and documentation | End-user training, knowledgebase maintenance, work estimation and on-call ownership are less explicit. ServiceNow appears in the title but the detailed requirements name .NET technologies. | Substantial fit to the detailed requirements. Treat ServiceNow as unresolved, not a proven platform disqualification. |
| Ferguson | Explicit UniBasic, Trilogie, APIs, SQL Server, Linux, testing and high-transaction systems | Interactive screens, phantom processes, dictionary design and multilevel file/trigger work are not demonstrated. Recent lead bullets focus on AI retrieval rather than ERP. | Some direct claims, but insufficient detail to establish extensive Pick/UniBasic expertise. |

## Specific bullets and what they communicate

### OnPay: the action is technical, but the business object is missing

**Bullet 1:** “Led enterprise delivery of applied AI workflows and customer-facing software, building ingestion and retrieval systems using Python, OpenAI API, and SQL under tight SLAs, improving demo readiness by ~60%.”

The tools fit part of the JD. The sentence does not establish a GTM workflow, CRM ownership, or a sales/marketing result. “Demo readiness” also needs a definition: time to prepare a demo, completed acceptance checks, or another measure? A percentage does not make an undefined outcome clear. This is supporting AI evidence, not the strongest opening proof for OnPay.

**Bullet 8:** “Built real-time routing and webhook workflows using REST APIs and JSON under 2-second processing SLAs, increasing routing accuracy by ~18% and reducing manual corrections across operations.”

This is closer to the JD. It states action, a measurable constraint and outcome. But the reader cannot tell whether the routed object is a sales lead, support case or transaction event. If it was lead routing, say so with the actual source/destination and rule. If it was transaction routing, preserve that context and present it as transferable experience.

**Bullet 10:** “Integrated internal systems via automated workflows and API connectors using webhooks and Zapier-style automation under security controls, accelerating cross-team handoffs and decreasing lead time by ~30%.”

“Zapier-style” does not demonstrate use of Zapier. The sentence also leaves both systems and the handoff unnamed. “Lead time” here may mean elapsed process time, not a sales lead. These ambiguities make apparent GTM alignment less convincing on close reading.

### BankPlus: good alignment, with a stronger bullet below the fold

**Bullet 7:** “Developed internal operational tooling using TypeScript, React, and Node.js under real-time constraints, cutting manual transaction reconciliation time by ~45% across a 200-member operations team.”

This is one of the better bullets: it identifies the business process, audience, stack and outcome. Reconciliation automation is directly relevant to the employer's general automation needs. The remaining opportunity is to name what the tool actually did. “Under real-time constraints” adds less than that feature detail would.

**Bullet 5:** “Authored system design and scalability plans for retrieval and caching tiers using Redis and PostgreSQL under SLA targets, increasing throughput capacity by ~3x for peak loads.”

There is a causal gap between authoring a plan and increasing capacity. If the candidate implemented the design and measured throughput, the sentence should describe that work. If only the plan was produced, the result should describe the plan's actual contribution rather than imply an implemented improvement.

**Bullet 12:** “Collaborated with product and SRE teams to design retry and backpressure strategies using Redis and Node.js under throughput limits, preventing ~3 major incidents during peak traffic.”

Retries/backpressure are relevant engineering decisions. “Preventing three major incidents” is difficult to evaluate unless it refers to three known failure modes reproduced and resolved in testing or another documented basis. A measured reduction in failures or validated load-test result would be easier to interpret if available. No replacement number should be invented.

### Ovative: the bullets actually cover much of the role

**Bullet 2:** “Architected ingestion pipelines with BigQuery, PostgreSQL and Docker under strict data retention constraints, reducing ETL latency by about 30% and improving downstream query performance for analytics.”

This is directly relevant: the employer asks for data engineering connected to a client-facing product. The sentence is understandable, and ETL latency is a relevant result. It could be stronger by identifying the pipeline change that reduced latency; the retention constraint matters only if it explains a design choice. The query-performance result is not quantified or explained, so the sentence may be trying to carry two accomplishments.

**Bullet 6:** “Mentored five engineers on testing best practices and containerized application code using pytest, Jest and Docker, improving CI pass rates by about 35% and reducing regressions post-release.”

This matches explicit mentoring, testing and container requirements. It deserves to stay if accurate. “Mentored on containerized application code” is awkward; identify the practice taught, such as how the team wrote tests or built containers, only if supported. Clarify whether the CI change is relative percent or percentage points when reporting that measure.

**Bullet 8:** “Implemented Node.js microservices with Kubernetes and Docker to validate streaming events under at-most-once constraints, increasing validation throughput by about 40% while maintaining system-wide 99% uptime.”

This has relevant backend/container keywords but raises questions about the design. Why was at-most-once delivery acceptable for validation? What protects correctness when an event is lost? Why emphasize 99% uptime as the reliability result? The sentence should explain the relevant trade-off, or omit the delivery-semantic detail if it does not help establish the accomplishment. It is not possible to declare the design wrong from this sentence alone.

### The Advocates: relevant evidence is present, but the opening sells a different specialty

**Bullet 4:** “Implemented data quality checks and retry logic in ETL pipelines using Python and GitHub Actions under compliance requirements, cutting failed ingestion events by about 60% month-over-month.”

This addresses the JD's reliability and data-pipeline responsibilities. It would be easier to assess if it identified the failed input or validation/retry change. Python can implement ETL, and GitHub Actions can orchestrate scheduled work; the sentence should clarify their roles rather than rely on the reader to infer them.

**Bullet 11:** “Integrated third-party identity checks and SSO flows using Azure AD and Okta under security policies, supporting 10% faster internal onboarding and reducing credential-related support tickets by ~35%.”

This is strong topical evidence for identity, security and internal operations. It is more relevant to this employer's daily work than a generic RAG opening. However, identity verification, SSO and account provisioning are different activities. Name the actual integration and avoid implying all three through the broad phrase “identity checks.”

The runbook/documentation bullets also align. The problem is not absence of relevant work; it is that AI ingestion dominates the first impression.

### Rothera: relevant frontend work needs visible feature detail

**Bullet 4:** “Developed React interfaces with Vite and CSS Modules for data-dense admin dashboards under accessibility and performance constraints, improving task completion and maintainability for client operators.”

This addresses the role directly. “Data-dense,” “accessibility” and “performance” remain labels until the reader sees the feature or fix. If supported by the actual work, the most useful details would be the specific tables/forms, state behavior, keyboard interaction or rendering technique. Do not add all of them merely because the JD mentions them.

**Bullet 7:** “Optimized front-end performance using Lighthouse and Web Vitals measurements, applying react-window for large lists under tight rendering budgets to improve perceived responsiveness.”

This is better technical evidence because react-window identifies a concrete intervention. It still lacks the measured rendering/user-interaction result, even though it says measurements were taken. A verified numeric result would help here; this is a case where XYZ is useful.

**Bullet 12:** “Instrumented frontend performance and testing using Jest and Lighthouse under performance budgets, reducing flakiness and ensuring internal tools met responsiveness expectations during operational peaks.”

This combines test reliability and UI performance. Jest and Lighthouse serve different purposes; neither name alone explains why tests became less flaky. Split the claims or retain the one for which the actual change can be described. “Ensuring expectations” is less informative than a named test or performance criterion.

### ASG: a real relevant bullet shows prototype scope, not production ownership

**Bullet 1:** “Led enterprise delivery of customer-facing AI software, building ingestion and retrieval systems and coordinated cross-functional teams using Python, TypeScript, and BigQuery to operationalize applied AI workflows across client accounts.”

The grammar is not parallel: “building ... and coordinated.” More importantly, the long opening establishes general AI delivery rather than ASG's central Clay/outbound responsibility.

**Bullet 7:** “Prototyped agentic GTM workflows in Clay and LangChain, combining enrichment signals with automated routing, validating feasibility under privacy constraints and informing RevOps playbook recommendations for adoption.”

This does address the role. “Prototyped” is appropriately specific about maturity, but the JD wants building and maintaining production Clay workflows and showing business impact. The sentence supports narrower experience; adding production language would not be justified without actual deployment. It should be prominent, and the candidate should explain the prototype's true scope.

### TreeHouse: tools match; ownership and outcomes need a clearer connection

**Bullet 6:** “Applied AI coding assistants and AI agents to accelerate development and automated unit testing in Python and TypeScript under release deadlines, reducing manual debugging and speeding feature delivery.”

The JD explicitly wants AI coding assistants, so this is relevant. The phrase “accelerate development and automated unit testing” is awkward and ambiguous. State whether the tools helped write tests, run tests, or investigate failures. “AI agents” and “coding assistants” need not both be included unless their roles differ.

**Bullet 7:** “Collaborated in Agile ceremonies, translated business requirements into data models and application backends using Microsoft SQL Server and ETL design under sprint constraints, enhancing product roadmap clarity and prioritization.”

It bundles meeting participation, requirements analysis, implementation and roadmap impact. The connection between ETL design and roadmap clarity is not explained. A focused example of a business request turned into a maintained application would better support the JD's ownership emphasis.

### Ferguson: distinguish direct evidence from resemblance

**Bullet 3:** “Implemented retrieval microservices using Oracle and SQL, optimizing UniQuery-like queries with application logging and monitoring under latency constraints and improving response predictability for search interfaces and analysts.”

“UniQuery-like” reads as resemblance, not direct UniQuery experience. Logging and monitoring can reveal a bottleneck, but the sentence does not identify the optimization. This is weak evidence for the specialist requirement.

**Bullet 7:** “Developed operational tooling and transaction validation workflows for real-time internal systems using UniBasic, Trilogie integrations, and GitHub under high-transaction constraints, improving consistency of internal transactions and reducing manual reconciliation.”

Unlike the previous bullet, this explicitly claims UniBasic work. It therefore should not be described as having no direct platform evidence. The weakness is specificity and depth: what program, screen, process or file structure was built? GitHub is supporting tooling; space would be better spent explaining the actual UniBasic work. Verify the claim, then describe the relevant implementation.

## Repeated sentence patterns

149 of 180 reviewed bullets contain the word **“under”**. This is an exact text count, not a measure of quality or AI authorship. The issue is that the same structure repeats:

> Action + system + tools + under constraints + improving/reducing outcome.

Useful constraints explain decisions: a concrete response-time limit, file-size restriction, privacy requirement or release compatibility condition. Phrases such as “under tight timelines,” “under stakeholder deadlines” and “under performance constraints” often add less than a description of the actual change.

Other recurring weaknesses:

- **Unspecified objects:** workflows, internal systems, operational tooling, customer-facing software. Say what was processed or what the user did, when that information is available.
- **Tool lists replacing implementation:** the reader learns Python/React/SQL but not the validation rule, synchronization behavior or UI feature.
- **Undefined outcomes:** demo readiness, routing accuracy, feedback velocity, mobile conversion proxy metrics. Define what changed; a percentage alone does not define the measure.
- **Activity/result gaps:** plans credited with throughput, Agile ceremonies credited with roadmap clarity, tooling credited with incident prevention without a visible mechanism.
- **Repetitive opening context:** AI ingestion and retrieval lead even when the job prioritizes frontend or CRM operations.

## Editing approach that preserves XYZ

These are sentence edits using only claims already present in the reviewed text. They are not independently verified accomplishments or new resumes ready for submission.

| Original example | Tighter wording | Remaining evidence question |
|---|---|---|
| OnPay reconciliation bullet | Automated transaction reconciliation with Python and SQL reporting, reducing weekly manual effort by approximately 65% and surfacing anomalies three times faster. | How were effort and detection speed measured? This still demonstrates transaction operations, not CRM ownership. |
| Ovative ETL bullet | Built ingestion pipelines with BigQuery, PostgreSQL and Docker, reducing ETL latency by approximately 30% while meeting data-retention requirements. | What pipeline change produced the improvement? |
| BankPlus reconciliation bullet | Built internal reconciliation tools with TypeScript, React and Node.js, reducing manual reconciliation time by approximately 45% for a 200-member operations team. | Which manual step did the tool automate? |
| Rothera rendering bullet | Improved large-list rendering in React using react-window, guided by Lighthouse and Web Vitals measurements. | Add the actual measured improvement only if available. |

Do not force a numeric result into every rewrite when the original has none. Preserve the intended quantified-bullet mix across the resume using results that can actually be supported.

## What to change first

1. **Choose the leading evidence by the employer's core work.** Ovative: product/data pipeline; BankPlus: reconciliation/process automation; The Advocates: integration reliability/identity; Rothera: admin UI; OnPay/ASG: actual CRM/Clay work, if available.
2. **Keep one accomplishment per sentence.** Make the action and its measured result refer to the same thing.
3. **Replace generic constraints with implementation detail where possible.** Keep constraints that explain a real design decision.
4. **Check the summary against the experience.** Every central specialist claim should have a clear example below it. Listing HubSpot, Clay or UniBasic is weaker than demonstrating the relevant workflow.
5. **Keep XYZ and vary sentence structure.** Retain meaningful numbers while removing repeated clause scaffolding and defining ambiguous metrics.

Writing quality is a plausible contributor to a weak first impression, especially where the role's core work is not demonstrated. It cannot explain all the outcomes: several reviewed resumes already show substantial requirement alignment, and their rejection emails do not identify sentence quality as the cause.
