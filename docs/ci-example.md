# Автосборка документов при изменении карты

Карта хранится в репозитории вместе с прошивкой или документацией. При каждом
изменении YAML CI проверяет карту и пересобирает PDF, Excel, DBC и C-заголовки.

## GitHub Actions

`.github/workflows/canmap.yml`:

```yaml
name: canmap
on:
  push:
    paths: ["canmap.yaml"]
  pull_request:
    paths: ["canmap.yaml"]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Install canmap
        run: uv tool install git+<адрес репозитория canmap>@v0.1.0
      - name: Validate
        run: canmap validate canmap.yaml --strict
      - name: Build
        run: canmap build canmap.yaml -o build
      - uses: actions/upload-artifact@v4
        with:
          name: signal-map
          path: build/
```

## GitLab CI

`.gitlab-ci.yml` (с Docker-образом canmap из внутреннего реестра):

```yaml
canmap:
  image:
    name: registry.example.local/tools/canmap:0.1.0
    entrypoint: [""]
  rules:
    - changes: [canmap.yaml]
  script:
    - canmap validate canmap.yaml --strict
    - canmap build canmap.yaml -o build
  artifacts:
    paths: [build/]
```

## Сгенерированный C-код в прошивке

Чтобы заголовки в прошивке не расходились с картой, их можно генерировать прямо
при сборке (CMake):

```cmake
add_custom_command(
  OUTPUT  ${CMAKE_BINARY_DIR}/canmap/bus1.h ${CMAKE_BINARY_DIR}/canmap/bus1.c
  COMMAND canmap gen c ${CMAKE_SOURCE_DIR}/canmap.yaml -o ${CMAKE_BINARY_DIR}/canmap --bus bus1
  DEPENDS ${CMAKE_SOURCE_DIR}/canmap.yaml
)
target_sources(firmware PRIVATE ${CMAKE_BINARY_DIR}/canmap/bus1.c)
target_include_directories(firmware PRIVATE ${CMAKE_BINARY_DIR}/canmap)
```

Или проверять в CI, что закоммиченные файлы совпадают с картой:

```sh
canmap gen c canmap.yaml -o firmware/canmap
git diff --exit-code firmware/canmap
```
