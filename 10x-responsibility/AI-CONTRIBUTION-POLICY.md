# AI-Assisted Contribution Policy

This project permits responsible use of AI-assisted development tools.

Using an AI system is not, by itself, a reason to accept or reject a
contribution.

The contributor who submits a change remains responsible for that
change.

## 1. Scope

This policy applies to the use of:

- code completion tools;
- conversational AI assistants;
- coding agents;
- automated refactoring tools;
- test generators;
- documentation generators;
- code translation tools;
- AI-assisted dependency migrations;
- systems that generate commits or pull requests.

Traditional formatters, compilers, linters, and deterministic code
generators are not normally treated as generative AI under this policy,
but their outputs remain subject to project review.

## 2. Permitted use

AI tools may be used for:

- exploring implementation approaches;
- explaining unfamiliar code;
- generating drafts;
- refactoring;
- writing tests;
- writing documentation;
- finding potential defects;
- translating code between languages;
- preparing migration plans;
- reducing repetitive work.

Permission to use AI does not imply automatic permission to merge its
output.

## 3. Contributor responsibility

By submitting AI-assisted work, the contributor confirms that they have
made a reasonable effort to:

- understand the submitted behavior;
- inspect the actual diff;
- remove irrelevant or fabricated code;
- verify APIs and dependencies;
- test important success and failure paths;
- consider security and privacy implications;
- confirm license and provenance compatibility;
- document important limitations;
- avoid including secrets or personal information.

The contributor, not the AI tool, is the point of contact for review.

## 4. Disclosure

Contributors should disclose material AI assistance when AI-generated
or AI-transformed content forms a meaningful part of a change.

Disclosure is normally not required for:

- spelling correction;
- trivial autocomplete;
- formatting;
- search;
- non-substantive wording changes.

Disclosure is expected when AI is used to:

- generate a substantial implementation;
- perform a cross-language port;
- produce security-sensitive code;
- generate or redesign public APIs;
- create substantial tests;
- perform repository-wide refactoring;
- generate dependencies or build configuration;
- autonomously prepare a pull request.

Disclosure should describe the role of AI and the human verification
performed.

Contributors are not required to publish complete prompts or private
conversations.

## 5. Prohibited practices

The following practices are not acceptable:

- submitting code the contributor cannot reasonably explain;
- submitting large generated changes without reviewing the diff;
- inventing test results, benchmarks, or compatibility claims;
- claiming that generated code was human-reviewed when it was not;
- using AI to remove or conceal license notices;
- submitting suspected copied code without resolving provenance;
- including secrets, credentials, or private data in prompts or commits;
- asking an AI system to bypass project safeguards;
- using generated tests only to create the appearance of coverage;
- representing experimental output as production-ready.

## 6. High-risk changes

AI-assisted changes in the following areas require explicit human review
from a qualified project reviewer:

- authentication and authorization;
- cryptography;
- secret management;
- input validation;
- deserialization;
- sandboxing;
- memory safety;
- build and release systems;
- package publication;
- data deletion or migration;
- personal data processing;
- remote code execution;
- safety-critical behavior.

The contributor should describe what was reviewed manually.

## 7. Tests and verification

AI-generated implementation code should normally be accompanied by
appropriate tests.

AI-generated tests must be independently reviewed for:

- meaningful assertions;
- missing failure cases;
- tests that simply mirror the implementation;
- overfitting to fixtures;
- fabricated APIs;
- incorrect mocks;
- non-deterministic behavior.

A passing generated test suite does not eliminate the need for
engineering review.

## 8. Dependency policy

AI tools may suggest nonexistent, outdated, vulnerable, or
inappropriately licensed dependencies.

Before adding a dependency, contributors must verify:

- that the package exists;
- that the package identity is correct;
- that the source and maintainer are credible;
- that the version is supported;
- that the license is compatible;
- that known vulnerabilities have been considered;
- that the dependency is actually necessary.

## 9. Privacy and confidential information

Contributors must not send the following to an external AI provider
without authorization:

- credentials;
- private keys;
- access tokens;
- unreleased vulnerability details;
- personal information;
- customer data;
- confidential business information;
- code that the contributor is not permitted to disclose.

Use of local or enterprise-approved tools does not remove the obligation
to handle information responsibly.

## 10. Maintainer response

Maintainers may:

- request an explanation of a submitted change;
- request additional tests or documentation;
- request that a large generated change be divided into smaller changes;
- require additional review;
- reject unverifiable or unmaintainable changes;
- revert generated changes that create unacceptable risk.

A contribution should not be rejected merely because AI was used.

The relevant questions are whether the contribution is understood,
lawful, reviewable, tested, useful, and maintainable.

## 11. Suggested disclosure format

Contributors may use the following format:

```text
AI assistance: Yes

Tool category:
- conversational assistant
- code completion
- coding agent
- code generator
- other

AI was used for:
- implementation draft
- tests
- documentation
- refactoring
- migration
- other

Human verification:
- reviewed the complete diff
- verified APIs and dependencies
- added or reviewed tests
- tested relevant failure paths
- performed security review
- documented known limitations