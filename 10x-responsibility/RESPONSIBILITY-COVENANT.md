# 10x Responsible Engineering Covenant v0.1

AI gives us the ability to produce software faster.

It does not transfer responsibility away from the people who submit,
review, merge, publish, operate, or maintain that software.

The purpose of this Covenant is not to prohibit AI-assisted development.
Its purpose is to prevent increased production speed from silently
becoming increased maintenance, security, and operational debt for
other people.

## 1. Responsibility follows submission

A person who submits a change assumes engineering accountability
within the project's contribution and review process for exercising
reasonable engineering judgment over that change, regardless of whether
it was produced by:

- the contributor personally;
- an AI assistant or coding agent;
- a code generator;
- a transpiler or automated migration tool;
- a contractor;
- an external example;
- another automated system.

“I did not write every line” does not mean “I have no responsibility
for what I submitted.”

AI systems cannot be assigned project ownership, review responsibility,
or maintenance accountability.

Adoption of this Covenant does not constitute a representation that the
software is secure, defect-free, production-ready, or suitable for any
particular purpose.

## 2. Understand before submitting

A contributor should be able to explain, at a level appropriate to the
size and risk of the change:

- what problem the change solves;
- why the change is needed;
- why the chosen implementation is appropriate;
- the important assumptions it makes;
- its major dependencies;
- its expected behavior;
- its important failure modes;
- how it was tested;
- how it can be disabled, removed, or rolled back.

This principle does not require a contributor to understand every
implementation detail of every dependency.

It requires sufficient understanding to make a responsible claim that
the change belongs in the project.

Code that cannot be reasonably explained should not be merged merely
because it compiles or passes existing tests.

## 3. Generated code receives no lower standard

AI-assisted code must meet the same standards as human-written code for:

- correctness;
- security;
- privacy;
- licensing;
- provenance;
- reviewability;
- documentation;
- testing;
- compatibility;
- accessibility;
- performance;
- maintainability.

A project must not lower its review standard merely because code was
produced quickly or automatically.

AI assistance is not an exemption from engineering review.

## 4. Disclose uncertainty

Contributors and maintainers should distinguish between:

- behavior that has been verified;
- behavior that has been tested only in limited environments;
- behavior inferred from documentation;
- behavior suggested by an AI system;
- behavior that remains unknown.

Experimental, partially understood, or narrowly tested code must not
knowingly be presented as production-ready.

Unknown limitations are acceptable.

Hidden limitations are not.

## 5. Tests are evidence, not understanding

Passing tests is useful evidence, but it does not by itself prove that a
change is correct, secure, maintainable, or fully understood.

Contributors should consider whether tests:

- exercise meaningful behavior;
- cover important failure paths;
- verify security boundaries;
- rely on overfitted fixtures;
- reproduce real user environments;
- were generated from the same mistaken assumptions as the code.

AI-generated tests must be reviewed with the same care as AI-generated
implementation code.

## 6. Do not silently externalize maintenance debt

Before adding code, contributors and reviewers should consider not only
the cost of creating it, but also the cost imposed on:

- future maintainers;
- downstream users;
- security responders;
- package distributors;
- operators;
- documentation teams;
- people responsible for migration and removal.

The ability to generate more code is not, by itself, a reason to add
more code.

Where reasonable, projects should prefer:

- smaller changes;
- fewer dependencies;
- simpler abstractions;
- explicit behavior;
- removable components;
- documented decisions;
- deletion over unnecessary expansion.

## 7. Maintenance is not permanent servitude

No contributor is required by this Covenant to maintain code forever.

Contributors and maintainers may step down.

When reasonably possible, a departing maintainer should:

- disclose that they are stepping down;
- update the project's maintenance status;
- identify currently supported versions;
- disclose known critical risks;
- document essential release and operational processes;
- identify a successor or state that no successor exists;
- provide a reasonable transition period when circumstances permit.

A maintainer has the right to leave.

A project has the duty to label its actual status honestly.

## 8. Publish an honest maintenance status

Projects following this Covenant should publish a clear maintenance
state.

Recommended states are:

- `active`
- `maintenance-mode`
- `security-only`
- `seeking-maintainer`
- `unmaintained`
- `archived`

A project must not knowingly represent itself as actively maintained
when it no longer has people able and willing to perform essential
maintenance.

An honest `unmaintained` status is not a violation of this Covenant.

## 9. Forking includes stewardship

Open-source users remain free to fork software according to its
applicable license.

A distributor of a modified version should clearly identify:

- that the version has been modified;
- whether it is maintained;
- who maintains it;
- which environments and versions are supported;
- where defects and security issues may be reported;
- whether it is affiliated with or endorsed by the upstream project.

A fork should not misrepresent its relationship with upstream or claim
support, testing, or security review that it has not received.

## 10. Security-relevant changes require greater care

The level of review should be proportionate to risk.

Changes involving the following areas should normally receive additional
human review:

- authentication;
- authorization;
- cryptography;
- secrets;
- sandboxing;
- deserialization;
- memory safety;
- input validation;
- dependency installation;
- package publishing;
- build and release infrastructure;
- personal or sensitive data;
- remote command execution;
- financial or safety-critical behavior.

AI-generated claims about security properties must not be accepted
without appropriate verification.

## 11. Provenance matters

Contributors should make a reasonable effort to ensure that submitted
materials may legally be included in the project.

When AI assistance is used, contributors remain responsible for
reviewing potential:

- license incompatibility;
- copied notices or comments;
- substantial similarity to external code;
- undocumented dependencies;
- generated secrets or credentials;
- attribution requirements.

A project may require disclosure of the type and extent of AI assistance.

A project should not require publication of private prompts, credentials,
personal information, proprietary context, or unrelated conversations
unless such material is genuinely necessary and may lawfully be shared.

## 12. Responsibility must remain proportionate

This Covenant must not be used to demand perfection, punish good-faith
mistakes, or impose unlimited personal liability on contributors.

Responsible engineering includes:

- admitting uncertainty;
- asking for review;
- reducing scope;
- reverting a change;
- documenting a limitation;
- declining work that cannot be safely completed;
- ending maintenance honestly.

The purpose of responsibility is to improve collective engineering
judgment, not to create a culture of fear.

## 13. Project enforcement

Projects may enforce this Covenant through:

- contribution review;
- branch protection;
- required tests;
- required human approval;
- provenance checks;
- documentation requirements;
- maintenance-status reviews;
- rejection or reversion of changes;
- suspension of contribution privileges for repeated misconduct.

Enforcement should be transparent, proportionate, and consistent.

Good-faith errors should ordinarily be addressed through correction and
learning.

Knowing misrepresentation, concealed provenance problems, fabricated
test claims, or repeated refusal to follow project safeguards may
justify stronger action.

## 14. Relationship to the software license

This Covenant is an engineering and community governance standard.

Unless a project explicitly states otherwise in a legally valid
agreement, this Covenant does not:

- modify the project's software license;
- reduce rights granted by an open-source license;
- create a restriction on fields of use;
- prohibit independent implementations;
- require contributors to work indefinitely;
- guarantee that software is fit for a particular purpose;
- replace applicable laws or professional obligations.

The software license governs permission to use, copy, modify, and
distribute the software.

This Covenant governs the standards under which a project accepts,
describes, and stewards contributions.

## Closing principle

Do not ask only:

> Can I make the machine write this?

Also ask:

> Who will understand, verify, operate, secure, and maintain it after I
> am gone?

**10x the speed. 10x the responsibility.**