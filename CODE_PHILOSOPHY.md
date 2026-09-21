# AGENTS.md

## Purpose

Write software that is enjoyable to read, enjoyable to change, and as simple as the problem allows.

This repository follows a DHH-inspired engineering philosophy: optimize for programmer happiness, prefer conventions and integrated systems, value beautiful and direct code, and resist complexity that exists only to satisfy fashion, abstraction, or hypothetical future needs.

These are principles, not religious laws. Respect the language, framework, and existing codebase. Do not force Ruby or Rails idioms into a stack where they do not belong.

---

## Core Philosophy

### 1. Optimize for programmer happiness

Code is written for humans first and machines second.

Prefer code that makes the next programmer think:

> Of course. That is exactly how this should work.

Choose clarity, expressiveness, good names, and pleasant APIs over clever machinery.

Do not accept developer misery as the inevitable price of "serious engineering."

---

### 2. Convention over configuration

Before adding configuration, ask whether the project can simply choose a sensible convention.

Prefer:

- one obvious project structure
- predictable names
- standard locations
- strong defaults
- fewer switches
- fewer environment-specific branches

Configuration is a cost. Every option creates another state the system can be in.

Add configuration only when there is a real requirement for variation.

---

### 3. The menu is omakase

Prefer a coherent, well-chosen stack over assembling many interchangeable pieces.

Use the framework and platform's intended path unless there is a concrete reason not to.

Do not replace working built-in capabilities merely because another library is fashionable.

Prefer one excellent default over five configurable alternatives.

---

### 4. Exalt beautiful code

Code aesthetics matter because code is read, maintained, debugged, and extended by people.

Beautiful code is usually:

- direct
- expressive
- compact without being cryptic
- unsurprising
- well named
- internally consistent

Do not dismiss readability or elegance as cosmetic concerns.

If two solutions are equally correct, prefer the one that is easier to understand at a glance.

---

### 5. Value integrated systems

Prefer systems whose parts are designed to work together.

Before introducing another service, process, framework, package, queue, database, abstraction layer, or build step, ask whether the existing system can solve the problem cleanly.

A dependency is not free. It adds:

- concepts
- upgrades
- failure modes
- configuration
- operational burden
- debugging surface

The default answer to a new dependency is "not yet."

---

### 6. Start with the monolith

A well-structured monolith is the default architecture.

Do not introduce microservices, distributed workflows, separate deployments, or network boundaries without evidence that the monolith is the problem.

Keep code close to the data and behavior it serves.

Extract a service only when an actual boundary has emerged, not because one might emerge later.

---

### 7. Prefer conceptual compression

Good abstractions should eliminate concepts, not merely move them around.

A useful abstraction makes the system easier to explain.

A bad abstraction requires learning:

1. the underlying mechanism
2. the abstraction
3. the mapping between them

Do not add layers whose only purpose is architectural ceremony.

---

### 8. Use sharp tools responsibly

Do not cripple the design merely to prevent every possible misuse.

Trust competent programmers.

Prefer powerful, expressive APIs with clear intent over defensive frameworks that make ordinary work painful.

Protect real trust boundaries: external input, permissions, secrets, destructive operations, money, and security-sensitive behavior.

Do not build guardrails around ordinary internal code just because misuse is theoretically possible.

---

### 9. Progress beats speculative stability

Do not preserve accidental complexity merely because it already exists.

When a simpler design becomes possible, prefer moving toward it.

Compatibility matters when users depend on it. Internal historical baggage does not deserve the same protection.

Delete obsolete code.

---

## Code Rules

### Write the simplest thing that completely solves the problem

Do not design for imaginary future requirements.

Avoid:

- speculative abstractions
- premature generalization
- unnecessary interfaces
- factories with one implementation
- wrapper classes that add no meaning
- configuration for values that never vary
- extension points nobody needs
- generic frameworks built for one concrete use case

Three clear lines of duplication can be better than the wrong abstraction.

Wait until the pattern is visible before extracting it.

---

### Prefer direct code over indirection

A reader should be able to follow the main path without jumping through many files.

Prefer:

```text
request -> domain behavior -> persistence -> response
```

over:

```text
request -> facade -> coordinator -> service -> adapter -> repository -> mapper -> persistence
```

unless those layers represent genuine domain or infrastructure boundaries.

Every indirection must earn its existence.

---

### Put behavior near the data it belongs to

Prefer rich domain objects over procedural code that reaches into passive data structures from far away.

A method should usually live on the object whose state and rules it represents.

Avoid turning the application into bags of data manipulated by unrelated "service" classes.

Use service objects when an operation genuinely spans concepts and has no natural home.

---

### Names should carry the design

Spend time naming things well.

Prefer domain language over technical language.

Good:

```text
subscription.cancel()
invoice.mark_paid()
recording.publish()
membership.expired?
```

Weaker:

```text
SubscriptionService.execute(...)
InvoiceManager.update_status(...)
RecordingProcessor.handle(...)
MembershipUtil.check(...)
```

Avoid vague words such as:

- manager
- processor
- handler
- helper
- utility
- data
- info

unless they are genuinely the clearest domain term.

---

### Keep methods focused, not artificially tiny

A method should represent one coherent idea.

Do not split readable code into many tiny methods merely to satisfy arbitrary line-count rules.

Extract when doing so:

- names an important concept
- removes meaningful duplication
- clarifies the main flow
- isolates a real boundary

Do not extract just to make a method shorter.

---

### Prefer readable conditionals

Optimize for the reader, not cleverness.

Use guard clauses when they make the happy path obvious.

Use a full `if/else` when there are genuinely two parallel branches.

Avoid dense boolean expressions and compressed control flow that require mental decoding.

---

### Comments explain why

Do not narrate obvious code.

Bad:

```text
# Increment count by one
count += 1
```

Good comments explain:

- a non-obvious constraint
- a deliberate trade-off
- compatibility behavior
- why a simpler-looking alternative is wrong
- external system behavior
- historical context that still matters

If a comment exists because the code is unclear, improve the code first.

---

### Prefer framework primitives

Before building custom infrastructure, check whether the language, framework, browser, operating system, database, or standard library already solves the problem.

Prefer native capabilities over dependencies when the native solution is sufficient.

Examples:

- database constraints over application-only invariants
- platform scheduling over custom schedulers
- standard HTTP semantics over proprietary protocols
- browser capabilities over unnecessary frontend packages
- framework conventions over custom plumbing

Own less code.

---

### Minimize build machinery

Do not introduce compilation, transpilation, code generation, bundling, preprocessing, orchestration, or bespoke build steps unless they deliver concrete value.

If source code can run directly, prefer that.

If the platform already understands the format, do not transform it merely because transformation is conventional elsewhere.

Every build step should justify its continued existence.

---

### Keep dependencies scarce

Before adding a dependency, answer:

1. What problem does it solve?
2. Can the standard library or existing stack solve it adequately?
3. Is the dependency simpler than the code it replaces?
4. What operational and upgrade burden does it introduce?
5. Is the project now coupled to this dependency's worldview?

Small dependencies can carry large conceptual costs.

---

### Do not create duplicate sources of truth

One fact should have one authoritative home.

Do not maintain manually synchronized copies of:

- configuration
- schemas
- command lists
- constants
- generated metadata
- state
- documentation that can derive from authoritative data

Derive secondary representations where practical.

---

## Architecture Rules

### Default hierarchy

When solving a problem, prefer this order:

1. Existing convention
2. Existing application code
3. Existing framework capability
4. Standard library / platform capability
5. Small local addition
6. Existing dependency
7. New dependency
8. New architectural component
9. New service or distributed system

The further down the list you go, the stronger the justification required.

---

### Database first for durable truth

The database is not an implementation detail.

Use it for what it is good at:

- constraints
- uniqueness
- transactions
- relations
- querying
- ordering
- durable state

Do not recreate weak versions of database guarantees in application code.

Avoid caches as authoritative state.

---

### Avoid premature distributed systems

Do not introduce queues, event buses, microservices, replicated state, or asynchronous workflows for work that can be completed simply and synchronously.

Asynchrony creates another timeline to reason about.

Use it when latency, reliability, throughput, or isolation actually requires it.

---

### Keep boundaries real

Good boundaries correspond to real differences:

- separate security domains
- different persistence systems
- external APIs
- independently operated systems
- clearly distinct business concepts

Do not invent boundaries solely to satisfy an architecture diagram.

---

## Refactoring Rules

### Make the change easy, then make the easy change

When existing structure fights the requested feature, first improve the structure enough that the feature fits naturally.

Do not bolt new behavior onto the wrong abstraction.

But keep preparatory refactoring tightly related to the task.

---

### Refactor toward fewer concepts

A refactor should usually leave the system with the same number or fewer concepts.

Be suspicious of refactors that introduce many new classes, interfaces, modules, or patterns without deleting equivalent complexity.

Measure improvement by comprehension, not file count.

---

### Delete aggressively

Remove:

- dead code
- unused flags
- obsolete compatibility paths
- abandoned experiments
- stale comments
- unnecessary abstractions
- dependencies no longer pulling their weight

Git remembers old code. The production codebase does not need to.

---

## Testing Rules

### Test behavior, not implementation ceremony

Tests should protect things users or other parts of the system rely on.

Prefer tests around:

- domain behavior
- important workflows
- regressions
- boundaries
- failure cases
- permissions
- data integrity

Avoid tests whose primary purpose is proving that mocks were called exactly as the current implementation happens to call them.

Refactoring internals should not require rewriting unrelated tests.

---

### Use the smallest useful test

Run focused tests for the code being changed.

Before considering work complete, run the relevant broader suite when practical.

For visual behavior, verify the result visually in addition to automated tests.

For bugs, prefer adding a regression test that fails before the fix and passes after it.

---

### Do not mock what you own without a reason

Prefer exercising real application objects together when practical.

Mocks are most useful at genuine external boundaries:

- third-party APIs
- network services
- expensive infrastructure
- time
- randomness

Do not turn internal implementation details into fake APIs merely to make unit tests possible.

---

## AI Agent Rules

### Read before writing

Before changing code:

1. inspect the relevant implementation
2. read nearby tests
3. identify existing conventions
4. search for similar behavior elsewhere in the repository
5. understand the actual call path

Do not guess an API that can be inspected.

---

### Preserve the house style

Match the surrounding code before applying generic preferences.

The local codebase outranks generic style advice.

Do not perform drive-by formatting, renaming, or refactoring unrelated to the task.

---

### Prefer surgical changes

Make the smallest coherent change that solves the problem well.

Do not turn a bug fix into an architecture rewrite.

Do not introduce a framework to implement a feature that needs a function.

Do not create extension points unless the task needs extension.

---

### Challenge accidental complexity

When asked to add something complicated, first determine whether the complexity is actually required.

If a simpler solution exists, choose it and state the trade-off.

Do not blindly implement architecture described in a prompt when the repository reveals a simpler path.

---

### Do not cargo-cult patterns

Never add something merely because "best practice" says so.

This includes:

- repositories
- service layers
- DTOs
- dependency injection containers
- interfaces
- event buses
- microservices
- factories
- builders
- state management libraries
- design patterns

Use a pattern when the problem demonstrates the need for it.

Patterns are names for solutions, not requirements.

---

### Prefer working software over architectural theater

A solution is good when it is:

- correct
- clear
- maintainable
- testable
- pleasant to work with

Not when it contains the maximum number of fashionable abstractions.

---

### Verify the result

Never declare work complete solely because the code looks plausible.

Run relevant:

- tests
- linters
- type checks
- builds
- executable examples

When the change affects a user-facing interface, inspect the actual result.

Report what was verified and what was not.

---

## Git Rules

Commits should be atomic.

Each commit should represent one coherent change.

Do not mix:

- unrelated refactoring
- formatting churn
- dependency upgrades
- feature work
- bug fixes

Write succinct commit messages that describe the change.

A commit message is one line, in the imperative mood ("Fix the race in X",
not "Fixed the race" or "This fixes the race"). Do not add a body, a
bullet-point breakdown, or an attribution/co-author line unless the user
explicitly asks for one on that commit.

Do not use destructive Git commands unless explicitly required and understood.

Never discard user changes.

---

## Dependency Rule

Before introducing a new package, service, framework, database, build tool, or abstraction, include a short justification in the implementation reasoning:

```text
Need:
Why the existing stack is insufficient:
Why this choice is the smallest adequate solution:
New operational/conceptual cost:
```

If that justification is weak, do not add it.

---

## Complexity Budget

Treat complexity like spending money.

A feature may justify complexity when the benefit is concrete.

Complexity must not be added merely because:

- the company may become huge
- traffic may increase someday
- another implementation may exist later
- a second database might be added
- the code might become a public library
- another team might need it
- microservices might eventually be useful

Solve today's real problem in a way that leaves tomorrow understandable.

---

## Final Review Checklist

Before finishing a change, ask:

- Is this the simplest complete solution?
- Did I follow the project's conventions?
- Did I add configuration where a convention would work?
- Did I add a dependency that the platform could replace?
- Did I introduce an abstraction before a pattern existed?
- Is the main execution path obvious?
- Are names expressed in domain language?
- Did I keep behavior close to the data it belongs to?
- Did I create duplicate sources of truth?
- Can any code, layer, option, or dependency now be deleted?
- Did I test the behavior that matters?
- Would I enjoy maintaining this code six months from now?

If the answer to the last question is no, improve the design before adding more machinery.

---

## North Star

Build software with taste.

Prefer clarity over ceremony.
Prefer conventions over options.
Prefer integrated tools over glue.
Prefer the monolith over premature distribution.
Prefer native capabilities over dependencies.
Prefer direct code over indirection.
Prefer meaningful abstractions over speculative ones.
Prefer deleting complexity over managing it.

The goal is not the fewest lines of code.

The goal is the fewest concepts necessary to make the software obvious.
