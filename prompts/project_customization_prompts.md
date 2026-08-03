# Agentic Framework Customization Prompts

Use these prompts to adapt this agentic framework to a specific business scope,
technology stack, operating model, and target architecture. Replace the values
inside brackets before using a prompt.

## 1. Scope Definition

Customize this agentic framework for a project in the [industry/domain] domain.
The main business goal is [goal]. Define the core user personas, operational
workflows, success metrics, and the minimum set of agents required for this
scope.

## 2. Architecture Fit

Review this framework against the target architecture: [describe architecture].
Identify which components should remain, which should be replaced, which should
be removed, and which new components are required.

## 3. Technology Stack Adaptation

Adapt the framework to use this technology stack: frontend [stack], backend
[stack], database [database], messaging [queue/event bus], observability
[tools], cloud [provider]. Provide the required code-level and configuration
changes.

## 4. Agent Role Design

Redesign the agent structure for this project scope: [scope]. Define each
agent's responsibility, input, output, tools, memory needs, escalation path, and
failure handling behavior.

## 5. Workflow Orchestration

Convert the current agent workflow into a production workflow for [use case].
Define the exact stages, decision points, approval gates, retry rules, timeout
rules, and human-in-the-loop controls.

## 6. Data Model Mapping

Map the framework's current incident and agent data models to this project's
domain entities: [entities]. Identify fields to add, fields to remove, schema
changes, validation rules, and migration concerns.

## 7. API Redesign

Redesign the API surface for [product/use case]. Define REST or event-driven
endpoints, request and response schemas, authentication requirements,
authorization rules, error contracts, and versioning strategy.

## 8. Frontend Experience

Transform the current dashboard into a professional UI for [target users].
Define the primary screens, navigation, key workflows, empty states, loading
states, accessibility requirements, and which demo-only elements must be removed.

## 9. RAG Strategy

Customize the RAG layer for [knowledge sources]. Define ingestion rules,
chunking strategy, metadata schema, retrieval filters, freshness requirements,
evaluation metrics, and fallback behavior when confidence is low.

## 10. LLM Provider Strategy

Adapt the LLM layer to use [provider/model]. Define prompt boundaries, model
selection rules, token limits, cost controls, output validation, retry handling,
and redaction requirements.

## 11. Tool Integration Plan

Identify the external tools this framework should integrate with for [scope],
including ticketing, chat, CI/CD, monitoring, cloud, databases, and internal
APIs. Define read actions, write actions, approval requirements, and audit
logging for each tool.

## 12. Security Hardening

Review the framework for production security. Recommend changes for secrets
management, authentication, authorization, input validation, prompt injection
defense, PII handling, audit logging, dependency scanning, and least-privilege
access.

## 13. Human Approval Model

Design the human approval model for [business process]. Define which actions can
run automatically, which actions require approval, who can approve them, what
context must be shown, and how approvals are recorded.

## 14. Observability Plan

Add production observability for the agentic workflow. Define logs, metrics,
traces, dashboards, alerts, correlation IDs, agent-level telemetry, LLM usage
tracking, and failure diagnostics.

## 15. Evaluation Framework

Create an evaluation plan for this agentic system. Define test datasets,
expected outputs, quality metrics, safety metrics, regression tests, human review
criteria, and release gates.

## 16. Deployment Architecture

Design the deployment architecture for [environment: local, staging,
production]. Include infrastructure components, environment variables, network
boundaries, CI/CD pipeline, rollback strategy, and operational runbooks.

## 17. Multi-Tenant Readiness

Adapt this framework for multi-tenant SaaS usage. Define tenant isolation,
database partitioning, authentication, role-based access control, per-tenant
configuration, rate limits, audit logs, and billing-relevant usage tracking.

## 18. Domain-Specific Agent Tools

For the domain [domain], define the domain-specific tools agents need. Include
tool purpose, input schema, output schema, permission level, failure modes, and
how each tool should be tested.

## 19. Production Gap Analysis

Compare the current repository with the requirements for a production-grade
[product/use case]. Produce a gap list covering code quality, architecture,
security, testing, documentation, UX, deployment, monitoring, and support
operations.

## 20. Release Preparation

Prepare this project for public release on GitHub and LinkedIn. Identify files
to clean up, secrets or generated artifacts to remove, README improvements,
license requirements, screenshots needed, setup instructions, and final
verification commands.
