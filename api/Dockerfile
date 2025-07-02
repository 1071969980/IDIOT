# use the project directory as the context directory
FROM python:3.13
WORKDIR /app

# Install uv package manager
RUN pip install uv -i "https://pypi.mirrors.ustc.edu.cn/simple/"

# Create app directory and initialize uv project
RUN mkdir -p /app && \
    cd /app && \
    uv init && \
    uv venv && \
    . .venv/bin/activate && \
    echo "Virtual environment is activated."

ENV UV_INDEX "https://pypi.mirrors.ustc.edu.cn/simple/"

# Copy requirements.txt and install dependencies
COPY requirements.txt /app/
RUN . .venv/bin/activate && \
    uv add -r requirements.txt

# Copy pip_resources directory and install packages
COPY pip_resources /app/pip_resources
RUN . .venv/bin/activate && \
    uv pip install /app/pip_resources/*.whl

# Copy project files
COPY ./api /app/api