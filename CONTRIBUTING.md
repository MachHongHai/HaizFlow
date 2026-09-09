# Contributing to HaizFlow

[Tiếng Việt](CONTRIBUTING.vi.md) · [Development guide](docs/development.md) · [Architecture](docs/architecture.md)

Focused bug reports and pull requests are welcome. Before working on a change, search existing issues and describe the user-visible problem, expected result, and scope.

## Development workflow

1. Create a branch from the current default branch.
2. Install the exact Windows environment with `scripts/install-desktop-env.ps1`.
3. Add a regression test for behavioral changes.
4. Keep network access, persisted data, cache signatures, and destructive actions explicit.
5. Run `scripts/test.ps1` before opening a pull request.
6. Update both English and Vietnamese documentation when user behavior changes.

Do not commit models, project media, runtime data, credentials, generated build output, or private logs. By submitting a contribution, you agree that it may be distributed under the repository's Apache-2.0 license.

For implementation conventions and release requirements, read the [development guide](docs/development.md) and [release readiness](docs/release-readiness.md).
