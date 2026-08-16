## Summary

Describe the change and why it is needed.

## Type of Change

- [ ] Documentation
- [ ] Bug fix
- [ ] Feature
- [ ] Test
- [ ] Refactor
- [ ] Security

## Areas Affected

- [ ] API
- [ ] UI
- [ ] Agents
- [ ] RAG
- [ ] LLM
- [ ] Approval
- [ ] Remediation
- [ ] Persistence
- [ ] Deployment
- [ ] Documentation

## Safety Checklist

- [ ] I did not commit `.env`, secrets, local logs, generated vector indexes, Terraform state, or build artifacts.
- [ ] New LLM or embedding inputs pass through the model egress sanitization layer.
- [ ] I did not include raw infra names, project paths, capacity details, PII, or secrets in prompts, embeddings, docs, tests, logs, or examples.
- [ ] Mock/local mode still works.
- [ ] New behavior is clearly labeled as implemented, partial, mocked, experimental, or planned.
- [ ] Documentation was updated where needed.
- [ ] Tests were added or updated where needed.

## Verification

List commands run:

```bash
pytest tests/ -q
```

## Notes for Reviewers

Include any risks, follow-up work, or known limitations.
