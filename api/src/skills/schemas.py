"""Schema-driven forms for Skills module."""

from src.form_models import Form, FormInput, FormInputType


def get_skill_upload_form() -> Form:
    return Form(
        form_name="Upload Skill (.zip)",
        submit_path="/skills/upload",
        form_inputs=[
            FormInput(
                input_type=FormInputType.FILE_UPLOAD,
                name="file",
                label="Skill Zip (.zip)",
                attr={
                    "accept": ".zip",
                },
            )
        ],
    )


def get_skill_manifest_form() -> Form:
    return Form(
        form_name="Create Skill (Manifest JSON)",
        submit_path="/skills/manifest",
        form_inputs=[
            FormInput(
                input_type=FormInputType.JSON,
                name="manifest_json",
                label="manifest.json",
                attr={
                    "placeholder": "Paste your manifest.json here",
                    "rows": "14",
                },
            ),
            FormInput(
                input_type=FormInputType.DYNAMIC_METADATA_SECRET,
                name="secrets",
                label="Secret variables",
                attr={
                    "placeholder": "Add secrets referenced by {{secret:NAME}} in manifest",
                },
            ),
            FormInput(
                input_type=FormInputType.TEXT_AREA,
                name="skill_md",
                label="SKILL.md (optional)",
                attr={
                    "placeholder": "Optional instructions/examples for the LLM",
                    "rows": "8",
                },
            ),
        ],
    )


def get_skill_manifest_edit_form(skill_id: str, version: str) -> Form:
    """Same as create form, but submits to update endpoint."""
    f = get_skill_manifest_form()
    f.form_name = f"Edit Skill (Manifest JSON) - {skill_id} v{version}"
    f.submit_path = f"/skills/{skill_id}/{version}"
    return f
