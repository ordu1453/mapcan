# Автосборка документов при изменении карты

Карта хранится в репозитории вместе с прошивкой или документацией. При каждом
изменении YAML CI проверяет карту и пересобирает PDF, Excel, DBC и C-заголовки.

## GitHub Actions

`.github/workflows/mapcan.yml`:

```yaml
name: mapcan
on:
  push:
    paths: ["my-map.yaml"]
  pull_request:
    paths: ["my-map.yaml"]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Install mapcan
        run: uv tool install git+<адрес репозитория mapcan>@v0.1.0
      - name: Validate
        run: mapcan validate my-map.yaml --strict
      - name: Build
        run: mapcan build my-map.yaml -o build
      - uses: actions/upload-artifact@v4
        with:
          name: signal-map
          path: build/
```

## GitLab CI

`.gitlab-ci.yml` (с Docker-образом mapcan из внутреннего реестра):

```yaml
mapcan:
  image:
    name: registry.example.local/tools/mapcan:0.1.0
    entrypoint: [""]
  rules:
    - changes: [my-map.yaml]
  script:
    - mapcan validate my-map.yaml --strict
    - mapcan build my-map.yaml -o build
  artifacts:
    paths: [build/]
```

## Сгенерированный C-код в прошивке

Чтобы заголовки в прошивке не расходились с картой, их можно генерировать прямо
при сборке (CMake):

```cmake
add_custom_command(
  OUTPUT  ${CMAKE_BINARY_DIR}/mapcan/bus1.h ${CMAKE_BINARY_DIR}/mapcan/bus1.c
  COMMAND mapcan gen c ${CMAKE_SOURCE_DIR}/my-map.yaml -o ${CMAKE_BINARY_DIR}/mapcan --bus bus1
  DEPENDS ${CMAKE_SOURCE_DIR}/my-map.yaml
)
target_sources(firmware PRIVATE ${CMAKE_BINARY_DIR}/mapcan/bus1.c)
target_include_directories(firmware PRIVATE ${CMAKE_BINARY_DIR}/mapcan)
```

Или проверять в CI, что закоммиченные файлы совпадают с картой:

```sh
mapcan gen c my-map.yaml -o firmware/mapcan
git diff --exit-code firmware/mapcan
```
