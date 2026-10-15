# The battery (bms) of examples/vehicle-can.yaml on Zephyr: its code is generated from the map at build time.
#   west build -b native_sim examples/zephyr -- -DZEPHYR_EXTRA_MODULES=<this repository>
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(mapcan_bms)

target_sources(app PRIVATE src/main.c)
mapcan_generate(MAP ../vehicle-can.yaml DEVICE bms)
