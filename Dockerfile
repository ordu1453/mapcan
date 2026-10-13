# Image for CI and server deployment.
# The PDF fonts are in the package, no system dependencies are needed.
#   docker build -t mapcan .
#   docker run --rm -v "$PWD:/work" mapcan build mapcan.yaml -o build
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/mapcan

WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE NOTICE THIRD_PARTY_NOTICES.md ./
# Every output and the editor (mapcan serve); not the app window and the language server
ARG EXTRAS="--extra web --extra pdf --extra xlsx"
RUN uv sync --locked --no-dev $EXTRAS --no-install-project
COPY src ./src
# The examples of the editor's start screen are in the package (force-include in pyproject.toml).
COPY examples ./examples
RUN uv sync --locked --no-dev $EXTRAS

ENV PATH="/opt/mapcan/bin:$PATH"
WORKDIR /work
ENTRYPOINT ["mapcan"]
CMD ["--help"]
