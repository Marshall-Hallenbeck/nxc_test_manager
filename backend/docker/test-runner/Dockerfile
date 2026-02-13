FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

WORKDIR /netexec

# Pre-clone and install dependencies from main branch at build time
# This creates a cached layer with all dependencies installed
RUN git clone --depth 1 https://github.com/Pennyw0rth/NetExec.git . && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction && \
    # Save the base poetry.lock for comparison
    cp poetry.lock /poetry.lock.base && \
    # Clean up everything - deps are installed in site-packages
    # Each PR will fetch fresh source files
    rm -rf /netexec/* /netexec/.[!.]* 2>/dev/null || true

WORKDIR /app

COPY run_tests.sh /app/run_tests.sh
RUN chmod +x /app/run_tests.sh

ENTRYPOINT ["/app/run_tests.sh"]
