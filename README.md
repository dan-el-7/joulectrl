# joulectrl

> **Find the lowest energy needed to get the job done on time.**

Local-first Linux tool: profile a repeatable workload, measure CPU-package energy and
runtime, select the lowest-energy measured configuration within a runtime budget, and
verify that selection with fresh executions.

- Product/technical spec: `docs/PLAN.md`
- Team coordination: `docs/TEAM_PLAN.md`
- Agent contract (binding): `AGENTS.md` · live state: `AGENTS2.md` · resume packets: `HANDOFF.md`
- Pre-verified demo-laptop hardware facts: `docs/VERIFIED_DEMO_LAPTOP.md`

The optimizer is entirely deterministic. An LLM is an optional explanation interface —
not a dependency, measurement source, or CPU controller.
