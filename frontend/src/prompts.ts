export const promptCategories = [
  { id: 'architecture', name: 'Architecture & design', description: 'Turn business goals into clear technical blueprints.' },
  { id: 'cloud', name: 'Cloud & modernization', description: 'Plan migrations, platforms and modernization.' },
  { id: 'ai', name: 'AI & knowledge', description: 'Design useful AI experiences with governed data.' },
  { id: 'integration', name: 'Data & integrations', description: 'Connect systems and build reliable data flows.' },
  { id: 'security', name: 'Security & resilience', description: 'Explore identity, protection and recovery.' },
  { id: 'delivery', name: 'Delivery & estimates', description: 'Make scope, effort and implementation plans explicit.' },
] as const;

export type PromptCategory = typeof promptCategories[number]['id'];
export type PromptTemplate = {
  id: string;
  category: PromptCategory;
  title: string;
  description: string;
  prompt: string;
  outputs: string[];
  cloud?: string;
  featured?: boolean;
};

export const promptTemplates: PromptTemplate[] = [
  {
    id: 'customer-portal', category: 'architecture', title: 'Customer self-service portal', featured: true,
    description: 'A complete starting point for a secure customer-facing application.',
    prompt: 'Design a customer self-service portal for [business domain] serving [number of users]. Include account management, service requests, notifications and integration with [existing systems]. Define functional and non-functional requirements, logical architecture, component responsibilities, API boundaries and key trade-offs. Provide a solution document, architecture diagram, delivery plan and indicative effort estimates. Ask about essential missing information and label all assumptions.',
    outputs: ['solution', 'diagrams', 'estimates', 'plan'],
  },
  {
    id: 'multi-tenant-saas', category: 'architecture', title: 'Multi-tenant SaaS platform',
    description: 'Explore tenant isolation, shared services and growth boundaries.',
    prompt: 'Design a multi-tenant SaaS platform for [product] with [expected tenants] and [users per tenant]. Compare tenant isolation approaches, define identity and authorization boundaries, data partitioning, tenant onboarding, audit logging and observability. Include a logical architecture diagram and explain trade-offs. Identify the scale, compliance and service-level details that need validation.',
    outputs: ['solution', 'diagrams'],
  },
  {
    id: 'architecture-review', category: 'architecture', title: 'Review an existing architecture',
    description: 'Use attached references to surface gaps and alternative designs.',
    prompt: 'Review the architecture described in my attached documents for [business goal]. Identify strengths, gaps, single points of failure, scaling constraints and security risks. Separate documented facts from assumptions. Prioritize recommendations by impact and effort, compare practical alternatives and cite the supplied reference passages. Provide a revised logical diagram where the documents contain enough information; otherwise ask focused questions.',
    outputs: ['solution', 'diagrams'],
  },
  {
    id: 'cloud-migration', category: 'cloud', title: 'Cloud modernization roadmap', featured: true,
    description: 'Move an existing application to the cloud in manageable phases.',
    prompt: 'Design a phased migration of [existing application and technology stack] from on-premises infrastructure to [target cloud]. Consider application dependencies, identity, networking, data migration, rollback, availability and operational ownership. Compare rehosting, replatforming and refactoring. Provide a target deployment diagram, migration waves, risks, implementation plan and indicative effort estimates. Do not assume verified cloud prices.',
    outputs: ['solution', 'diagrams', 'estimates', 'plan'],
  },
  {
    id: 'aws-platform', category: 'cloud', title: 'AWS application foundation', cloud: 'AWS',
    description: 'Outline an AWS hosting foundation around validated requirements.',
    prompt: 'Propose an AWS hosting foundation for [web application or API] with [traffic profile] and [availability target]. Describe networking, compute choices, deployment pipelines, identity, secrets, data services, monitoring, backup and recovery. Compare managed hosting options and explain the selection criteria. Include a deployment diagram and implementation phases. List the inputs needed to obtain current regional operating-cost quotes.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'hybrid-platform', category: 'cloud', title: 'Hybrid platform design', cloud: 'Hybrid',
    description: 'Connect cloud workloads with retained on-premises systems.',
    prompt: 'Design a hybrid platform connecting [cloud workloads] with [on-premises systems]. Evaluate connectivity, network segmentation, DNS, identity federation, data residency, latency, resilience and operational responsibilities. Include a deployment and connectivity diagram, dependencies, failure scenarios and a phased implementation plan. Ask for missing connectivity and recovery requirements.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'knowledge-portal', category: 'ai', title: 'Enterprise knowledge portal', featured: true, cloud: 'AWS',
    description: 'Bring together enterprise SSO, governed content and contextual AI search.',
    prompt: 'Design an AWS-hosted knowledge portal with enterprise SSO, team repositories, document approval workflows and contextual AI search. Address document access controls, ingestion, source citations, retrieval quality, prompt injection, monitoring and human review. Provide a detailed solution, logical architecture diagram, implementation plan and indicative effort estimates. Label assumptions and do not invent verified prices or benchmark results.',
    outputs: ['solution', 'diagrams', 'estimates', 'plan'],
  },
  {
    id: 'document-assistant', category: 'ai', title: 'Document question-answering assistant',
    description: 'Plan retrieval, citations, evaluation and permission-aware answers.',
    prompt: 'Design a question-answering assistant over [document sources] for [user groups]. Define ingestion, extraction and optional OCR, chunking, retrieval, permission filtering, source citations, model access and evaluation. Explain how to handle missing evidence, conflicting documents and instructions embedded in reference content. Include a data-flow diagram, risks and implementation plan. Treat all performance and cost targets as requiring validation.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'ai-workflow', category: 'ai', title: 'AI-assisted approval workflow',
    description: 'Add assistance to a process while retaining clear human accountability.',
    prompt: 'Design an AI-assisted workflow for [business process] where staff review and approve consequential actions. Define the AI role, human approval gates, permitted tools, data access, audit trail, failure handling and evaluation criteria. Show the workflow and system boundaries. Provide an implementation plan and distinguish automation opportunities from decisions that must remain under human control.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'event-integration', category: 'integration', title: 'Connected enterprise', featured: true,
    description: 'Connect CRM, ERP and commerce with reliable event-driven integration.',
    prompt: 'Design an event-driven integration platform connecting [CRM], [ERP] and [e-commerce platform]. Define data ownership, event contracts, delivery guarantees, idempotency, schema evolution, reconciliation, error recovery and monitoring. Include an integration diagram, alternatives, dependencies, delivery plan and indicative effort estimates. Clearly identify assumptions about volumes and existing interfaces.',
    outputs: ['solution', 'diagrams', 'estimates', 'plan'],
  },
  {
    id: 'analytics-platform', category: 'integration', title: 'Analytics data platform',
    description: 'Plan ingestion, governance and trusted analytical datasets.',
    prompt: 'Design an analytics platform combining [source systems] for [reporting and analytical goals]. Cover batch versus streaming ingestion, data quality, transformation, lineage, governance, access control, retention and consumption layers. Include a data-flow architecture diagram and phased implementation plan. Explain trade-offs and list the scale and freshness requirements needed for sizing.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'api-integration', category: 'integration', title: 'Partner API integration',
    description: 'Define a secure integration contract and operational failure paths.',
    prompt: 'Design an API integration between [internal application] and [partner system] for [business workflow]. Specify authentication, authorization, API contracts, validation, throttling, retries, idempotency, timeouts and observability. Include a sequence diagram showing success and failure paths, responsibilities, test strategy and implementation plan. Flag undocumented partner capabilities for validation.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'enterprise-sso', category: 'security', title: 'Enterprise identity & SSO', featured: true,
    description: 'Design sign-in, access boundaries and an auditable authorization model.',
    prompt: 'Design enterprise SSO and authorization for [application] using [identity provider]. Address OIDC or SAML selection, user provisioning, roles, least privilege, session lifecycle, service identities, audit events and account deactivation. Include an identity-flow diagram, implementation phases and validation questions. Distinguish design recommendations from compliance claims requiring independent review.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'disaster-recovery', category: 'security', title: 'Resilience & disaster recovery',
    description: 'Translate recovery goals into a testable operational design.',
    prompt: 'Create a resilience and disaster recovery design for [application and hosting environment] with target RTO [duration] and RPO [duration]. Identify failure domains, backup strategy, replication, failover, recovery dependencies, restore testing and incident roles. Include a deployment or recovery-flow diagram, trade-offs, exclusions and rollout plan. Do not describe recovery targets as achieved without test evidence.',
    outputs: ['solution', 'diagrams', 'plan'],
  },
  {
    id: 'security-review', category: 'security', title: 'Security design review',
    description: 'Review trust boundaries and practical mitigations using supplied evidence.',
    prompt: 'Review the attached solution design for security risks in [business context]. Map trust boundaries, sensitive data flows, identity and authorization, secrets, uploads, external integrations, logging and retention. Provide prioritized risks and mitigations, open questions and an implementation plan. Cite supplied passages, distinguish assumptions from facts and do not claim certification or legal compliance.',
    outputs: ['solution', 'plan'],
  },
  {
    id: 'delivery-estimate', category: 'delivery', title: 'Delivery plan & effort estimate', featured: true,
    description: 'Build a transparent estimate with roles, dependencies and uncertainty.',
    prompt: 'Using [requirements or attached solution], create an implementation plan and effort estimate. Break work into activities and required roles. Provide low, expected and high person-day effort, dependencies, confidence, exclusions and explicit contingency. Assume staffing of [FTE and roles] only after confirmation. Keep elapsed duration separate from effort. Use supplied daily rates [rates and currency] if available; otherwise leave implementation cost unpriced. Keep recurring operating costs separate.',
    outputs: ['solution', 'estimates', 'plan'],
  },
  {
    id: 'mvp-scope', category: 'delivery', title: 'Scope a practical MVP',
    description: 'Separate the essential first release from future expansion.',
    prompt: 'Define a practical MVP for [product idea] within [timeline and budget constraints]. Identify user journeys, essential capabilities, acceptance criteria, technical dependencies, key risks and explicit exclusions. Separate the first release from later phases, propose team roles and provide indicative low, expected and high person-day effort. Ask focused questions where missing information prevents a credible plan.',
    outputs: ['solution', 'estimates', 'plan'],
  },
  {
    id: 'executive-summary', category: 'delivery', title: 'Stakeholder solution presentation',
    description: 'Turn an architecture proposal into a decision-focused summary.',
    prompt: 'Using [solution requirements or attached architecture], prepare a stakeholder solution summary and presentation. Explain business objectives, proposed approach, key components, alternatives and trade-offs, implementation phases, assumptions, risks and decisions required. Include a clear conceptual architecture diagram. Keep technical detail appropriate for [audience] and distinguish indicative estimates from approved budgets.',
    outputs: ['solution', 'diagrams', 'plan', 'presentation'],
  },
];
