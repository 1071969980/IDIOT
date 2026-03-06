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

# Install JuiceFS
RUN curl -sSL https://d.juicefs.com/install | sh -

# Install JuiceFS Python SDK
COPY ./python_wheels/juicefs-0.1.0-py3-none-any.whl /python_wheels/juicefs-0.1.0-py3-none-any.whl
RUN . .venv/bin/activate && \
    uv add /python_wheels/juicefs-0.1.0-py3-none-any.whl

# clean up
RUN rm -rf /python_wheels

# Copy project files
COPY ./api /app/api

# Copy testcase files
COPY ./testcase /app/testcase