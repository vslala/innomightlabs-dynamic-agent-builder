FROM public.ecr.aws/lambda/python:3.13

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into the Lambda task root
RUN uv sync --frozen --no-dev --no-install-project

# Set PYTHONPATH to include the virtual environment site-packages and task root
ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/.venv/lib/python3.13/site-packages:${LAMBDA_TASK_ROOT}"

# Copy application code
COPY main.py ./
COPY lambdas ./lambdas
COPY src ./src

# Set the handler
CMD ["main.handler"]
