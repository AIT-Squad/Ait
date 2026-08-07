# 10x Responsible Engineering Covenant

> 10x the speed. 10x the responsibility.  
> 十倍速度，十倍责任。

AI can help us produce software faster, but it cannot assume
responsibility for understanding, reviewing, operating, securing,
and maintaining that software.

The 10x Responsible Engineering Covenant, abbreviated as **10xREC**,
is an open engineering responsibility standard for projects that use
AI-assisted development.

It is based on one simple principle:

> You may use AI to produce code.  
> You may not use AI to outsource responsibility.

## What 10xREC is

10xREC provides:

- an engineering responsibility manifesto;
- an AI contribution policy;
- a pull request responsibility checklist;
- a machine-readable project stewardship file;
- standard maintenance-status badges;
- a transparent process for maintainer transitions.

## What 10xREC is not

10xREC is not:

- a replacement for an open-source license;
- a restriction on whether contributors may use AI;
- a guarantee that software contains no defects;
- a requirement that contributors maintain code forever;
- a mechanism for making AI legally responsible;
- a certification of security or production readiness.

10xREC governs project contribution and stewardship practices.
The project's software license continues to govern the rights to use,
copy, modify, and distribute the software.

## Core principles

1. Responsibility follows submission.
2. Understand before you submit.
3. AI-generated code receives no lower standard.
4. Disclose uncertainty and known limitations.
5. Do not silently externalize maintenance debt.
6. Maintainers have the right to leave and the duty to label.
7. More code is not automatically more value.
8. Passing tests is not the same as understanding.

## Adoption

A project may adopt 10xREC by:

1. keeping its existing open-source license;
2. copying `RESPONSIBILITY-COVENANT.md` into the repository;
3. copying and adapting `AI-CONTRIBUTION-POLICY.md`;
4. adding the responsibility checklist to its pull request template;
5. creating a `STEWARDSHIP.yaml` file;
6. publishing the appropriate maintenance-status badge.

Add the following text to your project README:

```markdown
## Engineering responsibility

This project follows the
[10x Responsible Engineering Covenant](RESPONSIBILITY-COVENANT.md).

AI-assisted contributions are welcome, but contributors remain
responsible for reviewing, understanding, testing, and documenting
everything they submit.

**10x the speed. 10x the responsibility.**
```

## Suggested badge

```markdown
[![10xREC: Active Stewardship](https://img.shields.io/badge/10xREC-active%20stewardship-2ea44f)](STEWARDSHIP.yaml)
```

## Conformance levels

### 10xREC Declared

The project has published the Covenant and declared its intention to
follow it.

### 10xREC Practiced

The project also uses:

- an AI contribution policy;
- a responsibility checklist;
- a current `STEWARDSHIP.yaml`;
- documented security and maintenance contacts.

### 10xREC Verified

Reserved for a future independent verification program.

Self-adoption must not be described as independent certification.

## Project lifecycle labels

10xREC defines the following maintenance states:

- `active`
- `maintenance-mode`
- `security-only`
- `seeking-maintainer`
- `unmaintained`
- `archived`

An honest `unmaintained` label is not a mark of failure.

A project that clearly discloses that it is no longer maintained may be
more responsible than a project that appears active while silently
ignoring users and security reports.

## Versioning

This repository currently defines:

```text
10x Responsible Engineering Covenant v0.1
```

Projects should identify the version they have adopted.

## License

Unless otherwise stated, the documents and reusable templates in this
repository are licensed under Creative Commons Attribution 4.0
International.

When adopting the Covenant, attribution may be provided in the adopted
Covenant file or project documentation:

```text
Based on the 10x Responsible Engineering Covenant v0.1.
```

The Covenant does not change the license of an adopting project's code.