# Building documents in CI

Keep the signal map in the same repository as the firmware or the documentation it describes.
On every change to the YAML file, CI validates the map and rebuilds the PDF, Excel, DBC and C
artifacts, so the published documents always match the map.

The examples below assume the map is `my-map.yaml` at the repository root. Pin mapcan to a
released version (`vX.Y.Z`, see [Releases](https://github.com/ordu1453/mapcan/releases)) so that
builds are reproducible.

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
        run: uv tool install "mapcan @ git+https://github.com/ordu1453/mapcan@vX.Y.Z"
      - name: Validate
        run: mapcan validate my-map.yaml --strict
      - name: Build
        run: mapcan build my-map.yaml -o build
      - uses: actions/upload-artifact@v4
        with:
          name: signal-map
          path: build/
```

`--strict` fails the job on warnings as well as errors. Drop it if warnings should not block a
merge.

## GitLab CI

`.gitlab-ci.yml`, using the published Docker image:

```yaml
mapcan:
  image:
    name: ghcr.io/ordu1453/mapcan:X.Y.Z
    entrypoint: [""]
  rules:
    - changes: [my-map.yaml]
  script:
    - mapcan validate my-map.yaml --strict
    - mapcan build my-map.yaml -o build
  artifacts:
    paths: [build/]
```

The image's entrypoint is `mapcan`; GitLab needs it cleared (`entrypoint: [""]`) to run the
`script` commands. If the runners have no internet access, mirror the image to your internal
registry and reference it from there.

## Choosing what to build

`mapcan build` produces every format by default. Narrow it down, or build several PDF variants:

```sh
mapcan build my-map.yaml -o build --formats pdf,xlsx,dbc
mapcan build my-map.yaml -o build --pdf-template mapcan --pdf-template gost-2.105
```

## Generated C code in the firmware build

To keep the firmware headers in sync with the map, generate them as part of the build (CMake):

```cmake
add_custom_command(
  OUTPUT  ${CMAKE_BINARY_DIR}/mapcan/bus1.h ${CMAKE_BINARY_DIR}/mapcan/bus1.c
  COMMAND mapcan gen c ${CMAKE_SOURCE_DIR}/my-map.yaml -o ${CMAKE_BINARY_DIR}/mapcan --bus bus1
  DEPENDS ${CMAKE_SOURCE_DIR}/my-map.yaml
)
target_sources(firmware PRIVATE ${CMAKE_BINARY_DIR}/mapcan/bus1.c)
target_include_directories(firmware PRIVATE ${CMAKE_BINARY_DIR}/mapcan)
```

Alternatively, commit the generated files and let CI check that they still match the map:

```sh
mapcan gen c my-map.yaml -o firmware/mapcan
git diff --exit-code firmware/mapcan
```
