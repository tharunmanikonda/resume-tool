# AAA JD-only experiment — proposed experience draft

These project stories, responsibilities, technologies and numbers are generated examples, not verified employment history. All generated measurements are illustrative and unverified. This is a separate test artifact, not the saved resume.

## Target work

Member-facing mobile + web product lines (iOS, Android, React web)

Product-aligned sprints (2-week iterations) with cross-functional pairing, API-first back-end services, CI/CD, automated testing, and optional AI-assisted developer tooling

## Required characteristics

- Design and implement advanced features across mobile and web platforms
- Build and maintain high-performance, highly available, secure services and APIs with versioning
- Collaborate in Agile/XP teams including pair programming and code review
- Troubleshoot and resolve production issues; make independent technical decisions
- Use AI-powered development tools to accelerate code, debugging, and reviews (experience preferred)
- Continuously evaluate emerging technologies and recommend improvements

## Optional characteristics

- Experience designing agentic AI systems or LLM-integrated pipelines
- Consulting or freelance experience
- Prior exposure to Objective-C/legacy iOS stacks or MS web frameworks

## McKinsey & Company — Applied AI Engineer / Full Stack Developer

**Proposed scenario; not verified work history.**

**Project:** Cross-platform member personalization and notifications platform (mobile + web) with API gateway and microservice back end

**Workflow:** Design feature in sprint planning, implement API and platform components, pair-program UI, deploy via CI/CD, monitor post-release, iterate on feedback

### Generated bullets

- Designed and shipped a personalization API (v1→v2) that served per-member recommendation payloads to iOS/Android/web clients with header-based version negotiation
- Implemented server-side caching layer (Redis) and query batching that reduced median API response time from ~260ms to ~90ms for personalization endpoints
- Built client SDKs (TypeScript for web, Kotlin Multiplatform for Android and lightweight Swift wrappers for iOS) to standardize telemetry and graceful fallback for older app versions
- Led pair-programming sessions and code reviews across engineers, introducing AI-assisted review checks (Copilot + custom lint rules) that reduced review turnaround by ~35%
- Executed a rollout plan with canary deployments and automated health gates; identified and fixed a serialization bug that caused 4% of payloads to fail under peak writes
- Prototyped an agentic LLM orchestrator to draft admin-facing content and recommended actions; defined safety guardrails and a human-in-the-loop approval flow

### Assumptions

- Back end implemented in Java (Spring Boot) with PostgreSQL and Redis; deployed to Kubernetes
- Traffic profile modest (tens of thousands of daily users) for the scoped feature
- Used GitHub Actions for CI/CD and Datadog for observability
- AI tools used: GitHub Copilot, Claude Code for code suggestions; explored agentic AI with an LLM orchestrator prototype

## Uber — Full Stack Developer

**Proposed scenario; not verified work history.**

**Project:** Real-time booking and messaging subsystem supporting mobile clients and an admin web console

**Workflow:** Work scoped in iterations, pair with product designers and backend engineers, deliver API changes with migration path and monitor via dashboards

### Generated bullets

- Implemented a versioned booking API with schema migration strategy and adapter layer to support both v1 and v2 mobile clients during a 3-week migration window
- Optimized a messaging fan-out path by introducing batched event publishing and consumer-side idempotency checks, lowering peak CPU usage on the service by ~28%
- Authored 120+ typed unit and integration tests and adopted contract tests for downstream consumers, increasing CI coverage to ~78% for the service
- Led on-call triage for two P1 incidents: traced a memory leak to an upstream library, patched the consumer with a pooling fix and coordinated a library upgrade
- Introduced AI-assisted test scaffold generation and inline code suggestions (Cursor/Copilot), cutting initial test-writing time by ~40% for new endpoints
- Collaborated with UX and mobile engineers to design progressive enhancement on web and Android clients so critical booking flows remained functional under degraded network conditions

### Assumptions

- Backend services primarily Node.js + Java; message broker (Kafka) used for real-time events
- High concurrency: peak-side traffic in the hundreds of requests/sec for booking endpoints
- CI pipeline includes automated unit, integration, and load tests
- Used Cursor or Copilot Labs for test scaffolding and debugging assistance

## KPMG — Java Full Stack Developer

**Proposed scenario; not verified work history.**

**Project:** Enterprise customer-portal and reporting platform (web) with Java/Spring back end and Angular front end

**Workflow:** Requirements gathered by consulting leads, developer implements features and compliance controls, releases coordinated with client UAT

### Generated bullets

- Implemented role-based access controls and OAuth2 integration for three core reporting APIs, reducing unauthorized access vectors and satisfying client audit requirements
- Designed API versioning strategy using URI and header negotiation, enabling safe iterative release of reporting endpoints with documented client migration paths
- Refactored heavy database queries into materialized views and introduced connection pooling, which improved complex report generation latency by ~55%
- Built CI/CD pipelines that ran integration tests and deployed to staging with smoke-tests; reduced manual release steps from 12 to 4 actions
- Worked directly with consulting leads to translate client requirements into technical acceptance criteria and delivered demos during UAT windows

### Assumptions

- Primary stack: Java (Spring Boot), REST APIs, Angular 11+, OAuth2 for auth
- Clients required audit logging and role-based access controls
- Deployment on managed VMs or Kubernetes with Jenkins-based CI

## Trigent Software — Frontend Developer

**Proposed scenario; not verified work history.**

**Project:** Customer-facing marketing and account-management web application built with React

**Workflow:** Design handoff to front-end dev, implement components and integrate with REST APIs, run accessibility and performance audits, ship releases

### Generated bullets

- Rewrote a large account dashboard into code-split React components and lazy-loaded assets, cutting first-contentful-paint from ~2.8s to ~1.1s
- Implemented client-side retries with exponential backoff and a consistent error UX for REST failures, reducing support tickets tied to transient network errors by an estimated ~30%
- Added Jest + RTL unit tests and automated accessibility checks in CI, achieving a baseline component test coverage and catching regressions earlier in the pipeline

### Assumptions

- Front-end stack: React + Redux, Webpack, Jest + React Testing Library
- APIs were RESTful and managed by remote backend teams
- Performance budgets and basic WCAG a11y checks were part of acceptance criteria
