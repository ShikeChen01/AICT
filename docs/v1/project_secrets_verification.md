# Project Secret Tokens — Verification Against Plan

This document verifies the implementation part-by-part against the plan (see `.cursor/plans/project_secret_tokens_*.plan.md`). Tests live in `backend/tests/test_project_secrets.py`.

## 1. Storage

| Plan requirement | Implementation | Test |
|-----------------|----------------|------|
| `project_secrets` table scoped to `repository_id` | `backend/db/models.py`: `ProjectSecret` with `project_id` FK to `repositories.id` | `test_project_secret_model` |
| Columns: id, project_id, name, encrypted_value, hint, created_at, updated_at | Same model | `test_project_secret_model` |
| Unique (project_id, name) | `__table_args__` UniqueConstraint | `test_project_secret_unique_per_project_name` |
| Values stored encrypted (Fernet) when key set | `backend/db/repositories/project_secrets.py`: `encrypt_value` / `decrypt_value` | `test_encrypt_decrypt_fernet` |
| When key blank: store unencrypted (dev), warn in logs | Plain prefix `__plain__` + hint | `test_encrypt_decrypt_plaintext`, `test_decrypt_plain_prefix_without_key` |

## 2. Repository

| Plan requirement | Implementation | Test |
|-----------------|----------------|------|
| `list_for_project(project_id)` | `ProjectSecretsRepository.list_for_project` | `test_list_for_project_empty`, `test_list_for_project_returns_masked` |
| `upsert(project_id, name, value)` (create or update by name) | `ProjectSecretsRepository.upsert` | `test_upsert_creates_new`, `test_upsert_updates_existing` |
| `delete(project_id, name)` | `ProjectSecretsRepository.delete_by_name` | `test_delete_by_name` |
| `get_plaintext_values(project_id)` → `dict[str, str]` | `ProjectSecretsRepository.get_plaintext_values` | `test_get_plaintext_values_returns_dict`, `test_get_plaintext_values_decrypts_with_key` |

## 3. Schemas

| Plan requirement | Implementation | Test |
|-----------------|----------------|------|
| `ProjectSecretResponse`: id, name, hint, created_at (no value) | `backend/schemas/project_secrets.py` | `test_project_secret_response_schema` |
| `ProjectSecretUpsert`: name, value | Same file | `test_project_secret_upsert_schema`, `test_project_secret_upsert_schema_validates_name_and_value` |

## 4. API

| Plan requirement | Implementation | Test |
|-----------------|----------------|------|
| `GET /repositories/{id}/secrets` → list (masked) | `backend/api/v1/project_secrets.py` | `test_secrets_routes_registered`, `test_list_secrets_returns_masked_no_value` |
| `POST /repositories/{id}/secrets` → upsert | Same file | Routes registered |
| `DELETE /repositories/{id}/secrets/{name}` | Same file | Routes registered |
| Router registered in `router.py` | `backend/api/v1/router.py` includes `project_secrets_router` | `test_secrets_routes_registered` |

## 5. Config

| Plan requirement | Implementation | Test |
|-----------------|----------------|------|
| `secret_encryption_key: str = ""` in config | `backend/config.py` | `test_config_has_secret_encryption_key` |

## 6. Agent injection

| Plan requirement | Implementation | Test |
|-----------------|----------------|------|
| Loop loads project secrets at session start | `backend/workers/loop.py`: `ProjectSecretsRepository.get_plaintext_values(project.id)` | (integration: worker loop) |
| Pass to PromptAssembly | `PromptAssembly(..., project_secrets=project_secrets)` | — |
| `{project_secrets}` placeholder → KEY=VALUE lines | `backend/prompts/assembly.py`: `_resolve_placeholders(..., project_secrets)` | `test_resolve_placeholders_project_secrets_format`, `test_resolve_placeholders_project_secrets_empty`, `test_resolve_placeholders_project_secrets_none` |
| `secrets` block key in BLOCK_REGISTRY | `BLOCK_REGISTRY["secrets"]` | `test_assembly_block_registry_has_secrets` |
| Seed default secrets block (disabled) in new agents | `backend/db/repositories/agent_templates.py`: `_build_block_defs_for_role` appends secrets block | (covered by template/agent creation tests elsewhere) |

## 7. Frontend (no backend tests)

| Plan requirement | Implementation |
|-----------------|----------------|
| `listProjectSecrets`, `upsertProjectSecret`, `deleteProjectSecret` | `frontend/src/api/client.ts` |
| `ProjectSecret`, `ProjectSecretUpsert` types | `frontend/src/types/index.ts` |
| Settings section 8: table + add/update form + delete | `frontend/src/pages/Settings.tsx` |

## Running the tests

```bash
pytest backend/tests/test_project_secrets.py -v
```

All 22 tests should pass.
