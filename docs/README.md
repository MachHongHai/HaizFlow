# HaizFlow documentation

[English](README.md) · [Tiếng Việt](README.vi.md) · [Repository home](../README.md)

The documentation is separated by audience. User-facing guides favor direct instructions and visible outcomes; engineering documents define invariants, boundaries, and verification requirements.

| Start here | Audience | Scope |
| --- | --- | --- |
| [User guide](user-guide.md) | Users and testers | Installation, project workflows, editing, storage, and troubleshooting. |
| [Architecture](architecture.md) | Engineers | Components, data model, dependency direction, workers, caches, and security boundaries. |
| [Development guide](development.md) | Contributors | Reproducible environment, tests, QML/Python conventions, and pull requests. |
| [Manual editor engineering status](manual-editor-stabilization.md) | Maintainers | Implemented behavior, remaining acceptance work, and regression focus. |
| [Dependency security](dependency-security.md) | Security reviewers | Audit policy, pinned dependencies, exceptions, and mitigations. |
| [Release readiness](release-readiness.md) | Release maintainers | Legal, build, installer, and production gates. |

## Documentation policy

- English is the canonical first-language document. A matching `.vi.md` file provides Vietnamese guidance.
- Commands, paths, option names, schema fields, and error identifiers are not translated.
- User instructions describe actions and expected results without implementation jargon.
- Engineering documents use precise terminology and distinguish verified behavior from assumptions or planned work.
- Test counts and artifact sizes are not treated as permanent product facts; release evidence belongs in build metadata.
- Network, privacy, model-license, and compatibility limitations must be stated where they affect a decision.

For documentation corrections, open a [GitHub issue](https://github.com/MachHongHai/HaizFlow/issues).
