# Reality agent tools

`RealityAgent` is an optional orchestration layer over an already-open
`RealityModel`. It does not calculate geometry itself and does not turn model
names into asserted physical facts.

```python
import reality

model = reality.open("fixture.glb")
agent = reality.RealityAgent(model)
plan = agent.plan("move block x=200 mm")
preview = agent.preview(plan)       # copy-on-write validation only
result = agent.execute(plan)        # commits a new model only when valid
```

Tools are typed: `inspect`, `measure`, `edit`, and `create_box`. `inspect` and
`measure` return source-backed Reality data. `edit` invokes the existing
transactional `RealityModel.edit()` implementation. `create_box` creates real
Trimesh geometry from explicit caller dimensions.

## Safety contract

- The lifecycle is **plan → validate → preview → execute**.
- Unknown/ambiguous names and unsupported/unknown units reject the plan.
- Numeric edit parameters are parsed from the user request and recorded as
  user-supplied evidence. Providers cannot supply measured geometry facts.
- A failed edit or validation calls rollback and preserves the source model.
- `AgentProvider` is a small provider-neutral protocol intended only for tool
  selection/name disambiguation. No provider SDK or LLM dependency is required.

The built-in language parser is deliberately narrow and auditable; applications
can present their own UI and submit typed plans instead of natural language.
