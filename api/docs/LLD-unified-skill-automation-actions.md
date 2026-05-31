# Unified Skill Automation Actions

## Context

The platform already has a manifest-backed skill registry in `src/skills/registry.py`.
Agent skills install a manifest skill with validated config, store an installed skill instance, and call
the manifest action handler through the common signature:

```python
handler(arguments=..., config=..., context=...)
```

Automations also call skill handlers with the same signature, but their enablement model is separate:
`AutomationSkill` currently keys records by base `skill_id`, auto-enables only skills without install
forms, and therefore hides useful skills such as `send_email` from the action catalog until explicit
backend work or manual enablement happens.

## Goals

- Use `src/skills/*/manifest.yml` as the single source of truth for agent and automation skills.
- Make skills automation-compatible by default.
- Allow manifest-level opt-out with `automation.enabled: false`.
- Support repeatable automation skill instances using the same deterministic identity behavior as agent skills.
- Keep action handlers shared between agents and automations.
- Keep automation action arguments separate from skill install config:
  - install config is set when enabling/adding the skill instance to the automation
  - action arguments are set on the automation action node and may use smart values

## Manifest Contract

Add an optional manifest section:

```yaml
automation:
  enabled: true
```

The default is enabled. To opt out:

```yaml
automation:
  enabled: false
```

## Installed Skill Identity

Extract installed skill ID generation into `src/skills/identity.py`:

```python
def installed_skill_id_for(manifest: SkillManifest, normalized_config: dict[str, Any]) -> str:
    if not manifest.repeatable:
        return manifest.id
    identity_fields = manifest.repeatable_identity_fields or sorted(normalized_config.keys())
    digest = sha256(json.dumps(identity_values, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
    return f"{manifest.id}:{digest}"
```

Both `SkillService` and `AutomationService` use this helper.

## Automation Persistence

Align `AutomationSkill` with `AgentSkill`:

- `installed_skill_id`: unique per automation installed instance
- `skill_id`: base manifest skill ID
- DynamoDB key: `Skill#{installed_skill_id}`

Repository methods should treat their ID argument as `installed_skill_id`:

- `save_skill(skill)`
- `find_skill(automation_id, installed_skill_id)`
- `list_skills(automation_id)`
- `delete_skill(automation_id, installed_skill_id)`

Backward compatibility:

- Existing items without `installed_skill_id` read as `installed_skill_id = skill_id`.
- Existing action nodes with only `skill_id` can still resolve if exactly one enabled installed instance exists.
- If multiple instances exist for the base skill, old node configs fail clearly and ask for `installed_skill_id`.

## Automation Action Catalog

`GET /automations/{automation_id}/action-catalog` should return a complete skill action catalog.

For installed instances:

```json
{
  "action_type": "skill_action",
  "skill_id": "send_email",
  "installed_skill_id": "send_email:abc123",
  "skill_name": "Send Email",
  "action": "send",
  "available": true,
  "configured": true,
  "enabled": true,
  "disabled_reason": null
}
```

For not-yet-installed skills:

- If connectors are missing: show disabled with connector metadata.
- If install config is required: show disabled/config-required with install schema.
- If no install config is required: the skill can be auto-enabled and returned as available.

This keeps the UI generic and avoids hardcoding skill action availability.

## Runtime

Automation action nodes should prefer:

```json
{
  "action_type": "skill_action",
  "installed_skill_id": "send_email:abc123",
  "skill_id": "send_email",
  "action": "send",
  "arguments": {
    "subject": "Lead summary",
    "body": "<p>{{previous.body}}</p>"
  }
}
```

The runner resolves `installed_skill_id`, renders smart values in `arguments`, then calls:

```python
skill_registry.execute_action(
    skill_id=enabled.skill_id,
    action_name=action_name,
    arguments=rendered_arguments,
    config=automation_repo.get_skill_runtime_config(enabled),
    context=automation_context,
)
```

## Validation

Graph validation should:

- resolve installed skill instances by `installed_skill_id`
- support old `skill_id` only when unambiguous
- validate the base manifest exists
- enforce `manifest.automation.enabled`
- validate connectors
- validate action existence and required action arguments

## Implementation Steps

1. Add manifest `automation` config model.
2. Extract shared installed skill identity helper.
3. Add `installed_skill_id` to `AutomationSkill` and repository methods.
4. Update automation enable/update/delete/list responses and API paths to use installed instance IDs.
5. Update action catalog response to include availability/configuration fields.
6. Update graph validation and runner to resolve installed skill instances.
7. Add tests for repeatable automation skills, disabled connector actions, installed action catalog items, and ambiguous legacy configs.
