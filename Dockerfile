# Образ для CI и серверного развёртывания.
# Шрифты для PDF входят в пакет, системные зависимости не нужны.
#   docker build -t mapcan .
#   docker run --rm -v "$PWD:/work" mapcan build mapcan.yaml -o build
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/mapcan

WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
# Примеры для стартового экрана редактора входят в пакет (force-include в pyproject.toml).
COPY examples ./examples
RUN uv sync --locked --no-dev

ENV PATH="/opt/mapcan/bin:$PATH"
WORKDIR /work
ENTRYPOINT ["mapcan"]
CMD ["--help"]
