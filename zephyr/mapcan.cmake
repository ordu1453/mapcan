# mapcan_generate(MAP <map.yaml> [DEVICE <name>...] [BUS <name>...] [PREFIX <prefix>]
#                 [PHYS_TYPE float|double|int] [TARGET <cmake target>])
#
# Generates the C code of a CAN map with its Zephyr adapter (mapcan gen c --target zephyr) into the build
# folder and adds it to the target (app by default). With DEVICE the code of those devices: their frames, TX
# schedule, acceptance filters and dispatch; without it the code of the buses (BUS: only those). The map and
# the YAML files next to it are dependencies of the build configuration: a change regenerates the code.
#
# The mapcan command is taken from MAPCAN_EXECUTABLE, or found on the PATH (pip install mapcan).

function(mapcan_generate)
  cmake_parse_arguments(MAPCAN "" "MAP;PREFIX;PHYS_TYPE;TARGET" "DEVICE;BUS" ${ARGN})
  if(NOT MAPCAN_MAP)
    message(FATAL_ERROR "mapcan_generate: MAP is required")
  endif()
  if(DEFINED CONFIG_MAPCAN AND NOT CONFIG_MAPCAN)
    message(FATAL_ERROR "mapcan_generate: set CONFIG_MAPCAN=y")
  endif()
  if(NOT MAPCAN_TARGET)
    set(MAPCAN_TARGET app)
  endif()
  get_filename_component(map "${MAPCAN_MAP}" ABSOLUTE BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
  if(NOT EXISTS "${map}")
    message(FATAL_ERROR "mapcan_generate: map not found: ${map}")
  endif()
  find_program(MAPCAN_EXECUTABLE mapcan REQUIRED)

  set(out "${CMAKE_CURRENT_BINARY_DIR}/mapcan")
  set(args gen c "${map}" -o "${out}" --target zephyr)
  foreach(device IN LISTS MAPCAN_DEVICE)
    list(APPEND args --device "${device}")
  endforeach()
  foreach(bus IN LISTS MAPCAN_BUS)
    list(APPEND args --bus "${bus}")
  endforeach()
  if(MAPCAN_PREFIX)
    list(APPEND args --prefix "${MAPCAN_PREFIX}")
  endif()
  if(MAPCAN_PHYS_TYPE)
    list(APPEND args --phys-type "${MAPCAN_PHYS_TYPE}")
  endif()

  file(REMOVE_RECURSE "${out}")
  execute_process(COMMAND "${MAPCAN_EXECUTABLE}" ${args}
                  RESULT_VARIABLE rc OUTPUT_VARIABLE log ERROR_VARIABLE log)
  if(NOT rc EQUAL 0)
    message(FATAL_ERROR "mapcan gen c failed:\n${log}")
  endif()

  # The map and the files it may include (next to it and one level below) regenerate the code when changed
  get_filename_component(dir "${map}" DIRECTORY)
  file(GLOB maps "${dir}/*.yaml" "${dir}/*.yml" "${dir}/*/*.yaml" "${dir}/*/*.yml")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${map}" ${maps})

  file(GLOB sources "${out}/*.c")
  target_sources(${MAPCAN_TARGET} PRIVATE ${sources})
  target_include_directories(${MAPCAN_TARGET} PRIVATE "${out}")
endfunction()
