# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Purpose: run the official BidWeave MCP streamable HTTP service.
FROM python:3.12-slim
WORKDIR /app
COPY services/mcp/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.txt
COPY services/mcp /app/services/mcp
USER 65532:65532
ENV PYTHONUNBUFFERED=1
ENV CORE_API_URL=http://api:8000
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=5s --retries=12 CMD python -c "import http.client; c=http.client.HTTPConnection('127.0.0.1',8001,timeout=3); c.request('GET','/mcp'); assert c.getresponse().status == 401"
CMD ["uvicorn", "services.mcp.main:app", "--host", "0.0.0.0", "--port", "8001"]
