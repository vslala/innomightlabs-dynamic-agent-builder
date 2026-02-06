"""Schema-driven forms for Skills module."""

from src.form_models import Form, FormInput, FormInputType


def get_skill_upload_form() -> Form:
    return Form(
        form_name="Upload Skill",
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
