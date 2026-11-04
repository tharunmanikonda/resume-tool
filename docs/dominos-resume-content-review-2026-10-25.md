# Domino’s Software Engineer II: content review

Reviewed the latest saved draft, updated October 25, 2026 at 19:02:05, with output folder `Domino's - Software Engineer II (2)`. Sources: the draft’s saved job description, final resume snapshot, analysis and review metadata. This is a local content assessment, not a new model-generated audit or a prediction of an employer’s screening decision.

## Verdict

The resume has useful engineering evidence and several coherent sections, but it does not yet deliver the intended JD-to-project-to-bullet alignment. It primarily presents an AI/backend engineer for a posting that explicitly includes substantial native app qualifications. Swift appears in the summary, skills and genuine native projects, so native experience is not absent. The problem is its prominence and depth relative to the posting.

The numerical XYZ goal is not itself the problem. Preserve supported measurements. Improve what each measurement describes and whether the implementation plausibly caused the stated result. Numbers showing scale, such as transactions processed, are useful context but do not independently demonstrate an improvement.

## JD and story alignment

The JD combines general software engineering duties with explicit native app qualifications: Kotlin and/or Swift, native development environments, REST/JSON consumption, testing, architecture patterns, accessibility, analytics, notifications/location, build tools and app-store publishing.

The stored analysis assigns `role_family = backend application engineering` and `generation_route_key = backend_application`. It recognizes Swift among the top requirements, but its core problem and system description remain generic. This is evidence of a mismatch in this draft’s interpretation; a complete code trace would be needed to establish exactly which generation stage caused the final selection.

The strongest supported positioning is software engineering across backend systems **with native Swift project experience**. Do not turn backend employment into fictional mobile employment. Prioritize SmartHealth iOS and NotchSafe over the RAG project, and surface supported SwiftUI/CoreML evidence where relevant. Do not add Xcode, mobile release ownership, MVVM, accessibility or push notifications merely because the JD requests them.

## Experience: every bullet

Numbering follows the order within each employer in the saved resume.

| Bullet | Assessment | Required improvement |
| --- | --- | --- |
| McKinsey 1: secure LLM gateway, 18% API overhead | Relevant security and performance work. The opening joins two actions awkwardly: “Productionized …, added …”. “API overhead” is undefined. | Identify whether 18% measures latency, cost, compute or another recorded quantity. Connect the mechanism to that specific result; do not guess. |
| McKinsey 2: Node.js/FastAPI referral APIs, sub-second responses | Useful service development evidence. “Scalable,” “high load” and “AI workflows” leave the actual responsibility vague. | Name the referral operation and implemented change. Add load or latency definition only if known. |
| McKinsey 3: CI/CD static analysis, 15% more edge cases | Relevant testing/quality contribution, and the former duplicated accomplishment is absent from this version. | Define the comparison and what counted as an identified edge case. Automated analysis does not establish mentoring or human PR-review experience. |
| McKinsey 4: F1 0.72 to 0.86, 120 fewer weekly tickets | Contains a concrete evaluation metric, but the classification-to-support outcome needs explanation. | Confirm how better classification reduced those tickets and how the change was measured. The sentence currently implies direct causality. |
| McKinsey 5: product/analytics A/B experiments | Credible collaboration, but generic and overlaps the surrounding evaluation story. | Identify the feature decision, experiment contribution or resulting change. A qualitative result can work if specific. |
| McKinsey 6: referral classification, 5,000 to 7,000 interactions | Names a business system, but “prompt-evaluated classification pipelines” is hard to interpret and “through pipeline improvements” adds no mechanism. | Explain the actual pipeline change and distinguish usage growth from processing capacity. Confirm the connection to adoption. |
| Uber 1: Isolation Forest trip audits, 200,000 weekly trips | A clear system, method and operating scale. Among the stronger bullets. | Clarify the audit outcome if supported; trip volume describes scope rather than detection quality. |
| Uber 2: Python feature normalization | Fits the trip-anomaly story, but “consistency and model stability” are broad outcomes. | Explain the data problem corrected, such as a specific normalization or validation issue, using actual evidence. |
| Uber 3: semantic caching, 1M transactions, 32% lower inference latency | Has an implementation and outcome, but its relationship to the trip-audit system is unexplained. | Identify what was embedded/cached and what inference workload benefited. It may be a separate valid project; do not force an unsupported connection to Isolation Forest. |
| Uber 4: Kafka/Python fare verification, 75,000 daily bookings | Clear workflow, mechanism and scale. Strong transferable distributed-system evidence. | Clarify how fare verification relates to trip audits if they shared a system; otherwise present it as a distinct contribution. |
| Uber 5: dashboards reducing UI latency to 1.2 seconds | The causal mechanism is missing. Dashboards observe behavior; an intervention is needed to explain the reduction. Model inference and UI latency are also different measures. | Name the actual optimization and measurement if known. Otherwise limit the claim to monitoring/diagnosis and report the measured latency without implying the dashboard caused an improvement. |
| KPMG 1: JSP/Thymeleaf dashboards, 120 KPIs | Concrete audit-product context, but “Formulated dashboard views” is unnatural. | Use “Built” or “Developed.” Confirm whether both rendering technologies applied to these views. “Real-time” needs support beyond displaying dashboards. |
| KPMG 2: Spring Boot/PostgreSQL APIs, ten applications | Clear and relevant backend contribution. | Clarify the exchange/synchronization mechanism if available. “Ensuring consistent synchronization” is stronger than simply implementing REST endpoints. |
| KPMG 3: JWT authentication, 50,000 transactions | Authentication work and transaction scale are useful. “Preventing data integrity failures” is not explained by JWT authentication alone. | Describe supported access-control behavior. Retain integrity claims only with the actual validation, authorization or transactional mechanism that produced them. |
| KPMG 4: S3/Python document workflows, 15,000 files | Coherent audit-document workflow with useful scale. | Explain how traceability was implemented if that result is claimed; storage/retrieval automation alone does not establish an audit trail. |
| KPMG 5: modular services, 200 developer hours | Good maintainability theme and a potentially useful outcome. | State the measurement period or calculation if available. Separate the refactoring’s effect from the unrelated fact that Thymeleaf renders views. |
| Trigent 1: jQuery-to-React migration, ten pages | Clear action and scope; reusable components support the maintainability story. | Clarify the actual error reduction if measured. Otherwise keep the supported structural improvement without a broad unmeasured outcome. |
| Trigent 2: Figma layouts, fifteen mockups/five device types | Clear frontend delivery and compatibility scope. | Distinguish device types from browsers or viewport sizes if needed. Responsive web work should not imply native mobile experience. |
| Trigent 3: Jest tests, fifteen regressions | Strong quality contribution with a concrete result. | Tests detect failures; the developer fixes defects. Change the wording to distinguish detecting regressions from fixing them. |

## Coherent narratives

- **McKinsey:** An enterprise referral system is a plausible anchor. Gateway security, referral APIs and intent classification can support that story if they actually belong to the same system. The resume does not clearly establish that relationship. CI/CD quality work can remain a separate contribution. Avoid making every bullet repeat “AI,” “LLM,” “prompt” or “pipeline” when the engineering action is what matters.
- **Uber:** Ingestion, normalization, anomaly detection and monitoring can form a trip-audit narrative. Fare verification may be adjacent or separate. Semantic caching needs its own explained workload; the current text does not connect it to the rest.
- **KPMG:** The clearest existing product narrative: audit dashboards, APIs, access control, compliance documents and maintainability. Some individual claims still overstate what their mechanisms establish.
- **Trigent:** A coherent frontend modernization story: migration, responsive implementation and regression testing. It is concise and understandable.

## Projects and summary

SmartHealth is the most directly relevant iOS project; NotchSafe supplies concrete Swift/SwiftUI native implementation details. The RAG project currently appears first and has four bullets, increasing the AI emphasis before the reader reaches either native project.

The RAG project also repeats sub-500ms semantic-search performance across two bullets. S3 storage alone does not explain search latency. The claimed 40% development-cycle reduction from Copilot/Cursor needs a defined comparison. In NotchSafe, a binary under 5 MB measures package size, not runtime memory; clipboard monitoring does not by itself explain the small binary. In SmartHealth, the user-activity input and native implementation could be clearer, and “real-time” needs an actual responsiveness basis.

The summary is a long inventory of languages, platforms and capabilities. It mentions Swift but leads the reader through backend services and AI workflows before native projects. A shorter opening should establish the supported engineering identity and native project evidence, followed by the most relevant implementation strengths. SwiftUI is supported by the saved project evidence but absent from the skills list. Relevance should determine selection; avoid adding every available technology.

## Review reliability

The stored review reports zero numerical Trigent bullets, although all three visible bullets contain quantities. Follow-up tracing established that this is a number-recognition defect: the checker misses written numbers and some modified numeric expressions. It is not evidence of an old review by itself. Some requirement explanations also reference source accomplishments omitted from the final resume, such as Uber fallback/rate-control reliability work. Source evidence can justify a proposed addition, but it does not mean the submitted document communicates that capability. Do not treat the saved score of 82 as independent validation of this final version.

Follow-up tracing also recovered full contribution plans and narratives in the saved original version. The reviewed active entries omit those fields through canonicalization. Revision 4 becoming revision 5 is the normal review-patch transition, not proof of a stale audit. See `docs/dominos-call-trace-2026-10-25.md` for the live replay and corrected attribution.

## Fix order

1. Interpret the explicit native app qualifications as central when selecting the story and projects, while preserving truthful employment history.
2. Make each employer’s system/workflow understandable and explain separate projects rather than implying connections unsupported by evidence.
3. Repair ambiguous metrics and causal claims, especially Uber latency, KPMG integrity, and McKinsey overhead/adoption.
4. Put the native projects first and remove repeated project outcomes.
5. Review the final assembled content, including project selection and order, rather than crediting facts that exist only in the source profile. Preserve the numerical target as a writing preference, using supported measurements.
