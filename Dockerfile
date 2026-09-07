FROM cgr.dev/chainguard/python:latest-dev@sha256:c23539f80289046e2fa734d3f3fc418833fc22d064a50cc43fa9a6edc28c1615 AS builder

WORKDIR /app

COPY --chown=65532:65532 requirements.txt .
RUN python -m pip install --no-cache-dir --user -r requirements.txt

COPY --chown=65532:65532 app ./app
RUN mkdir -p /app/data

FROM cgr.dev/chainguard/python:latest@sha256:1f37785e5cdb70151f36aaa15e1e3cef4571424dbefbf4b0d8a9222535cb13ff

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder --chown=65532:65532 /home/nonroot/.local /home/nonroot/.local
COPY --from=builder --chown=65532:65532 /app/app ./app
COPY --from=builder --chown=65532:65532 /app/data ./data

CMD ["-m", "app.main"]
