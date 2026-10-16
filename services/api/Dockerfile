# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed build recipe; no warranty.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.8.22
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY bidweave ./bidweave
COPY migrations ./migrations
RUN uv sync --frozen --no-dev \
    && mkdir -p /data/history \
    && chown -R 65532:65532 /data
ENV PATH="/app/.venv/bin:$PATH"
USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "bidweave.main:app", "--host", "0.0.0.0", "--port", "8000"]
