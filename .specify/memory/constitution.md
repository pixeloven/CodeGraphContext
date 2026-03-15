<!--
SYNC IMPACT REPORT
==================
Version change: [TEMPLATE] → 1.0.0
Modified principles: N/A (initial ratification — all principles are new)
Added sections:
  - Core Principles (5 principles)
  - Technology Constraints
  - Contribution Standards
  - Governance
Removed sections: N/A (no prior content)
Templates reviewed:
  - .specify/templates/plan-template.md     ✅ Constitution Check section present; gates derive from principles below
  - .specify/templates/spec-template.md     ✅ User story structure and acceptance scenarios align with Testing Pyramid
  - .specify/templates/tasks-template.md    ✅ Phase structure reflects test-first and pyramid principles
  - .specify/templates/agent-file-template.md ✅ No outdated agent-specific references found
Follow-up TODOs: None — all placeholders resolved.
-->

# CodeGraphContext Constitution

## Core Principles

### I. Graph-First Architecture

All code intelligence MUST be represented as a property graph of typed nodes (functions,
classes, files, modules) and typed relationships (CALLS, IMPORTS, INHERITS, DEFINES).
New parsers and indexers MUST produce graph-compatible output — flat or ad-hoc data
structures are not acceptable as the final output of any indexing step.
The graph schema (node labels, relationship types, and their required properties) is the
canonical source of truth; all CLI commands, MCP tools, and query logic MUST derive from
it, not duplicate or contradict it.

**Rationale**: The entire value proposition of CGC is queryable graph context. Deviating
from graph-first design undermines the core product contract with AI agents and users.

### II. Dual Interface — CLI and MCP

Every user-facing capability MUST be accessible via both the `cgc` CLI (Typer/Click) and
the MCP server tool API. Neither interface may lag behind the other; a capability that
exists in one MUST exist in the other within the same release. CLI commands output to
stdout (human-readable by default, JSON when `--json` flag supplied); errors go to stderr.

**Rationale**: Users rely on CGC in both interactive terminal sessions and automated AI
assistant pipelines. Parity between the two interfaces prevents feature silos and ensures
the tool is universally accessible regardless of integration context.

### III. Testing Pyramid (NON-NEGOTIABLE)

CGC follows a strict testing pyramid:

- **Unit** (`tests/unit/`): Fast (<100ms), heavily mocked, covers isolated components.
- **Integration** (`tests/integration/`): Covers interaction between 2+ components with
  partial mocking (~1s).
- **E2E** (`tests/e2e/`): Full user journey tests with minimal mocking (>10s).

All new features MUST include tests at the appropriate pyramid level(s) before merging.
`./tests/run_tests.sh fast` (unit + integration) MUST pass locally before any PR is
submitted. Tests for a feature MUST be written and observed to fail before implementation
begins (Red-Green-Refactor).

**Rationale**: CGC's correctness guarantees — that graph queries return accurate, complete
context — can only be trusted with comprehensive, layered test coverage. Untested parsers
or query paths create silent failures that degrade AI agent output quality.

### IV. Multi-Language Parser Parity

Every programming language supported by CGC MUST expose the same canonical node types
(Function, Class, File, Module, Variable) and the same relationship types (CALLS, IMPORTS,
INHERITS, DEFINES) where applicable to the language. Language-specific parsers MAY add
language-native relationship types (e.g., IMPLEMENTS for Java interfaces) only if they
are documented in the graph schema and do not break cross-language queries. A parser MUST
NOT introduce schema deviations (renamed labels, different property keys) without a
migration plan approved via the amendment process.

**Rationale**: Users and AI agents query the graph without knowing which language produced
the data. Schema inconsistency across parsers would produce unreliable query results and
break tooling that depends on stable node/relationship contracts.

### V. Simplicity

Implement the simplest solution that satisfies the current requirement. YAGNI (You Aren't
Gonna Need It) applies strictly: abstractions, helpers, and new modules MUST be justified
by a current, concrete need — not anticipated future requirements. Three similar lines of
code are preferable to a premature abstraction. Complexity in the graph schema, parser
logic, or query layer MUST be justified in the plan document before implementation.

**Rationale**: CGC serves a broad contributor base across many languages and stacks.
Unnecessary complexity raises the barrier to contribution, increases maintenance cost, and
makes the graph schema harder to reason about.

## Technology Constraints

CGC's core technology choices are stable and MUST NOT be replaced without a major
constitutional amendment:

- **Language**: Python 3.10+ (no other implementation languages for the core library)
- **Parsing**: Tree-sitter (the sole AST parsing mechanism; regex-based parsing is
  prohibited for language node extraction)
- **Protocol**: Model Context Protocol (MCP) for AI agent integration
- **Graph Database**: FalkorDB (embedded/default) or Neo4j (production); the database
  abstraction layer MUST support both without feature disparity
- **CLI Framework**: Typer / Click
- **Package Distribution**: PyPI (`codegraphcontext`)

New runtime dependencies MUST be added to `pyproject.toml` (or equivalent) and MUST be
justified in the PR description. Dependencies that significantly increase install size or
reduce cross-platform compatibility require explicit maintainer approval.

## Contribution Standards

All contributors MUST adhere to the following standards:

- **Code style**: Follow existing project conventions; run linting before submitting.
- **PR scope**: Each pull request MUST be focused on a single feature or bug fix.
- **Test gate**: `./tests/run_tests.sh fast` MUST pass before PR submission.
- **Documentation**: New CLI commands and MCP tools MUST be documented in `docs/`.
- **Security**: Vulnerabilities MUST be reported privately (see `SECURITY.md`); do not
  open public issues for security findings. Dependencies MUST be kept up to date.
- **Breaking changes**: Any change to the graph schema, CLI command signatures, or MCP
  tool API signatures is a breaking change and requires a MAJOR version bump and a
  migration guide.

## Governance

This constitution supersedes all other development practices documented in this repository.
In the event of a conflict between this document and any other guideline, this constitution
takes precedence.

**Amendment procedure**:
1. Open a GitHub issue proposing the amendment with rationale.
2. Allow at least one maintainer review cycle.
3. Update this file, increment the version per the versioning policy, and set
   `Last Amended` to the date of the change.
4. Propagate changes to dependent templates (per the Consistency Propagation Checklist
   in `.specify/templates/constitution-template.md`).

**Versioning policy**:
- MAJOR: Backward-incompatible governance changes, principle removals, or redefinitions.
- MINOR: New principle or section added, or materially expanded guidance.
- PATCH: Clarifications, wording fixes, non-semantic refinements.

**Compliance review**: All PRs MUST be reviewed against Core Principles I–V. Reviewers
MUST reject PRs that violate any non-negotiable principle without documented justification
in a Complexity Tracking section (see plan template).

**Version**: 1.0.0 | **Ratified**: 2025-08-17 | **Last Amended**: 2026-03-14
