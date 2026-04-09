# Pull Request

## Summary

Brief description of what this PR does.

Closes #ISSUE_NUMBER

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Infrastructure / CI / tooling
- [ ] Documentation
- [ ] Breaking change (fix or feature that would cause existing functionality to change)

## Changes made

- Change 1
- Change 2

## Checklist

- [ ] My code follows the project style (`ruff check` + `ruff format` pass)
- [ ] I have added/updated type hints and `mypy --strict` passes
- [ ] I have added tests that prove my fix/feature works
- [ ] All new and existing tests pass (`pytest -v`)
- [ ] I have updated documentation if needed
- [ ] I have updated `CHANGELOG.md` under `[Unreleased]`

## Testing

Describe how you tested these changes:

```text
uv run pytest -v --tb=short
uv run ruff check src/ tests/
uv run mypy src/
```

## Screenshots / Logs

If applicable, add screenshots or paste relevant output.
