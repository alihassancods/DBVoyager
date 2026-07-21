# DBVoyager Development Instructions

> This document defines the engineering principles and coding standards for every contribution to DBVoyager. Every generated file, module, class, and function must comply with these instructions.

---

# Core Philosophy

DBVoyager is an enterprise-grade AI platform.

The goal is **not** to produce working code as quickly as possible.

The goal is to produce software that is:

* Modular
* Reusable
* Extensible
* Testable
* Type-safe
* Maintainable
* Production-ready

Every design decision should prioritize long-term maintainability over short-term convenience.

---

# General Principles

## 1. Never Rewrite Existing Code

Before generating new code:

* Search the existing codebase.
* Reuse existing modules whenever possible.
* Extend existing abstractions instead of duplicating logic.
* Refactor only when necessary.
* Avoid creating parallel implementations of the same feature.

If existing functionality satisfies the requirement, reuse it.

---

## 2. Prefer Composition Over Duplication

Every feature should build upon existing components.

Never duplicate:

* Database logic
* Business logic
* Validation
* Parsing
* Utility functions
* Configuration handling
* Logging

If duplicate logic is detected, extract it into a reusable module.

---

## 3. Single Responsibility Principle

Every module should have one responsibility.

Every class should have one responsibility.

Every function should perform one logical task.

Avoid large classes and large functions.

---

## 4. Modular Architecture

Organize code into logical modules.

Bad

```text
database.py
```

Good

```text
database/
    connector.py
    metadata.py
    models.py
    scanner.py
    repository.py
```

Each module should represent a coherent subsystem.

---

# Pydantic First

Every data object exchanged between modules must be represented by a Pydantic model.

Examples include:

* Requests
* Responses
* Configuration
* Tool Inputs
* Tool Outputs
* Agent Messages
* Metadata
* Investigation Results
* Reports
* Events

Never pass dictionaries when a Pydantic model is appropriate.

Never return anonymous dictionaries.

Use strongly typed models.

---

# Strong Typing

All code must use type hints.

Every function must declare:

* Parameter types
* Return type

Avoid:

* Any
* Dynamic typing
* Untyped dictionaries

Prefer explicit domain models.

---

# Domain Models

Represent business concepts as models.

Examples

* Investigation
* DatabaseSchema
* BusinessEntity
* ToolRequest
* ToolResult
* InvestigationPlan
* Evidence
* Recommendation

Business logic should operate on domain objects rather than raw dictionaries.

---

# Project Structure

Organize code by feature rather than file type whenever practical.

Example

```text
agents/
tools/
database/
memory/
planner/
investigation/
conversation/
visualization/
health/
reports/
api/
core/
shared/
```

Each package should expose a clear public interface.

---

# Keep Files Small

Files should remain focused.

Target

* Less than 300 lines when practical
* Split files before they become difficult to navigate

Large files indicate multiple responsibilities.

---

# Dependency Direction

Lower-level modules must never depend on higher-level modules.

Example

Allowed

```text
Planner

↓

Database
```

Not allowed

```text
Database

↓

Planner
```

Keep dependencies flowing inward toward core abstractions.

---

# Separation of Concerns

Separate:

* API
* Business Logic
* Data Access
* AI Logic
* Tool Logic
* Persistence
* Configuration

Never mix responsibilities.

---

# Configuration

Never hardcode:

* API keys
* URLs
* Ports
* Model names
* Database credentials
* File paths
* Timeouts

Everything should be configurable.

---

# Logging

Never use print statements.

Use structured logging.

Logs should provide enough information to debug production issues.

---

# Error Handling

Never silently ignore exceptions.

Catch only exceptions that can be handled.

Provide meaningful error messages.

Preserve stack traces where appropriate.

Never hide failures.

---

# Validation

Validate all external inputs.

Assume every external input is invalid until proven otherwise.

Use Pydantic validation whenever possible.

---

# Asynchronous Code

Use asynchronous code for:

* Database operations
* Network requests
* AI calls
* File operations

Avoid blocking operations.

---

# Database Access

Never scatter SQL throughout the codebase.

All database interaction should be encapsulated.

Business logic must not know SQL implementation details.

---

# AI Integration

AI components should never directly access infrastructure.

Instead

Agent

↓

Tool

↓

Infrastructure

Agents reason.

Tools execute.

Infrastructure performs work.

---

# Tool Design

Every tool should have:

* Input Model
* Output Model
* Clear responsibility
* Deterministic behavior
* Independent testing capability

Tools should never communicate with each other directly.

The orchestrator coordinates tools.

---

# Agent Design

Agents should:

* Think
* Plan
* Decide
* Coordinate

Agents should not:

* Query databases directly
* Read files directly
* Access infrastructure directly

Agents must use tools.

---

# API Design

Endpoints should be thin.

They should:

* Validate input
* Invoke services
* Return typed responses

Business logic must never live inside route handlers.

---

# Service Layer

Business rules belong in services.

Services should coordinate multiple repositories and tools.

Services should remain independent of HTTP frameworks.

---

# Repository Layer

Repositories own persistence.

Repositories should never contain business logic.

---

# Utility Modules

Utility modules should contain only generic reusable functionality.

They must never depend on business-specific modules.

---

# Reusability

Before writing new functionality ask:

* Does something similar already exist?
* Can an existing abstraction be extended?
* Can this become a shared component?

Prefer extension over duplication.

---

# Documentation

Every public class should include:

* Purpose
* Responsibilities
* Important assumptions

Complex logic should explain *why*, not *what*.

Avoid unnecessary comments.

Well-written code should remain readable.

---

# Future Compatibility

Every feature should be designed assuming DBVoyager will eventually become:

* Multi-agent
* Multi-user
* Multi-database
* Plugin-based
* Distributed
* Cloud-native

Avoid decisions that make future evolution difficult.

---

# Extensibility

Design extension points.

Do not hardcode:

* Database types
* AI providers
* Report formats
* Visualization engines
* Tool registries

Future implementations should be added rather than replacing existing code.

---

# Testing Mindset

Write code that is easy to test.

Avoid hidden state.

Avoid global variables.

Prefer dependency injection.

Design deterministic components.

---

# Code Quality Checklist

Before completing any task, verify:

* Existing code has been reused where possible.
* No duplicate implementations were introduced.
* Pydantic models are used for all data contracts.
* Functions are strongly typed.
* Responsibilities are clearly separated.
* Business logic is isolated from infrastructure.
* Modules remain cohesive.
* Configuration is externalized.
* Logging and error handling are implemented.
* Code is extensible and compatible with future platform growth.
* New functionality integrates cleanly with the existing architecture.

Every contribution should improve the architecture rather than increase technical debt.
