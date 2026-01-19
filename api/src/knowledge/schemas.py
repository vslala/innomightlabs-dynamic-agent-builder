"""
Knowledge Base and Crawl Job form schemas.
"""

from src.form_models import Form, FormInput, FormInputType, SelectOption


# Source type options
SOURCE_TYPE_OPTIONS = [
    SelectOption(value="sitemap", label="Sitemap URL"),
    SelectOption(value="url", label="Starting URL (Crawl)"),
]

# Chunking strategy options
CHUNKING_STRATEGY_OPTIONS = [
    SelectOption(value="hierarchical", label="Hierarchical (Recommended)"),
]


def get_crawl_config_form(kb_id: str) -> Form:
    """
    Get the form schema for configuring a crawl job.

    Args:
        kb_id: The knowledge base ID for the submit path

    Returns:
        Form schema for crawl configuration
    """
    return Form(
        form_name="Crawl Configuration",
        submit_path=f"/knowledge-bases/{kb_id}/crawl-jobs",
        form_inputs=[
            FormInput(
                label="Source Type",
                name="source_type",
                options=SOURCE_TYPE_OPTIONS,
                value="sitemap",
                input_type=FormInputType.SELECT,
            ),
            FormInput(
                label="URL",
                name="source_url",
                input_type=FormInputType.TEXT,
                attr={
                    "placeholder": "https://example.com/sitemap.xml",
                },
            ),
            FormInput(
                label="Max Pages",
                name="max_pages",
                value="100",
                input_type=FormInputType.TEXT,
                attr={
                    "type": "number",
                    "min": "1",
                    "max": "1000",
                },
            ),
            FormInput(
                label="Max Depth (for URL crawling)",
                name="max_depth",
                value="3",
                input_type=FormInputType.TEXT,
                attr={
                    "type": "number",
                    "min": "1",
                    "max": "10",
                },
            ),
            FormInput(
                label="Rate Limit (ms between requests)",
                name="rate_limit_ms",
                value="1000",
                input_type=FormInputType.TEXT,
                attr={
                    "type": "number",
                    "min": "100",
                    "max": "10000",
                },
            ),
            FormInput(
                label="Chunking Strategy",
                name="chunking_strategy",
                options=CHUNKING_STRATEGY_OPTIONS,
                value="hierarchical",
                input_type=FormInputType.SELECT,
            ),
        ],
    )


# Static version for validation
CRAWL_CONFIG_FORM = Form(
    form_name="Crawl Configuration",
    submit_path="/knowledge-bases/{kb_id}/crawl-jobs",
    form_inputs=[
        FormInput(
            label="Source Type",
            name="source_type",
            options=SOURCE_TYPE_OPTIONS,
            value="sitemap",
            input_type=FormInputType.SELECT,
        ),
        FormInput(
            label="URL",
            name="source_url",
            input_type=FormInputType.TEXT,
        ),
        FormInput(
            label="Max Pages",
            name="max_pages",
            value="100",
            input_type=FormInputType.TEXT,
        ),
        FormInput(
            label="Max Depth (for URL crawling)",
            name="max_depth",
            value="3",
            input_type=FormInputType.TEXT,
        ),
        FormInput(
            label="Rate Limit (ms between requests)",
            name="rate_limit_ms",
            value="1000",
            input_type=FormInputType.TEXT,
        ),
        FormInput(
            label="Chunking Strategy",
            name="chunking_strategy",
            options=CHUNKING_STRATEGY_OPTIONS,
            value="hierarchical",
            input_type=FormInputType.SELECT,
        ),
    ],
)


def get_create_knowledge_base_form() -> Form:
    """
    Get the form schema for creating a knowledge base.

    Returns:
        Form schema for knowledge base creation
    """
    return Form(
        form_name="Create Knowledge Base",
        submit_path="/knowledge-bases",
        form_inputs=[
            FormInput(
                label="Name",
                name="name",
                input_type=FormInputType.TEXT,
                attr={
                    "placeholder": "My Knowledge Base",
                },
            ),
            FormInput(
                label="Description",
                name="description",
                input_type=FormInputType.TEXT_AREA,
                attr={
                    "placeholder": "A brief description of what this knowledge base contains...",
                },
            ),
        ],
    )


CREATE_KNOWLEDGE_BASE_FORM = get_create_knowledge_base_form()
