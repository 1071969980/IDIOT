# use the project directory as the context directory
FROM python:3.13

ARG UV_INDEX_URL=https://pypi.mirrors.ustc.edu.cn/simple/
ENV UV_DEFAULT_INDEX=$UV_INDEX_URL

WORKDIR /app

# Install uv and create the application virtual environment
RUN pip install uv -i "$UV_INDEX_URL" && \
    uv venv /app/.venv

# Install locked runtime dependencies. The exported requirements file contains
# hashes, so --require-hashes verifies every downloaded artifact.
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /app/.venv/bin/python \
        -r /app/requirements.txt \
        --require-hashes

# Install JuiceFS
RUN curl -sSL https://d.juicefs.com/install | sh -

# Install JuiceFS Python SDK
COPY ./python_wheels/juicefs-0.1.0-py3-none-any.whl /tmp/wheels/juicefs-0.1.0-py3-none-any.whl
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /app/.venv/bin/python \
        /tmp/wheels/juicefs-0.1.0-py3-none-any.whl

# Copy project files
COPY ./api /app/api
