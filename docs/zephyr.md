# Zephyr RTOS

`mapcan gen c --target zephyr` writes, next to the driver-independent code, an adapter to the CAN API of
Zephyr (`<zephyr/drivers/can.h>`, Zephyr 3.6 and later): `<base>_zephyr.h` and `<base>_zephyr.c`. The
driver-independent code does not change; the adapter is a thin layer on top of it.

For every frame:

* `<frame>_to_can_frame(&msg, &frame)`: packs a message into a `struct can_frame` with its ID, the flags
  `CAN_FRAME_IDE`, `CAN_FRAME_FDF`, `CAN_FRAME_BRS` and the DLC (`can_bytes_to_dlc()`);
* `<frame>_from_can_frame(&msg, &frame)`: unpacks a received one, after checking its ID and format.

Frames longer than 8 bytes need `CONFIG_CAN_FD_MODE`. A J1939 PGN sent with the transport protocol is not
one CAN frame and has no conversion.

With `--device` (the code of one device, see [cli.md](cli.md#code-of-one-device)) the adapter also has:

* `<device>_zephyr_rx_filters[]`, the `struct can_filter` of the frames the device receives, and
  `<device>_zephyr_add_rx_filters(can, &msgq)`, which installs them with a queue of frames;
* `<device>_zephyr_dispatch(&rx, &frame)`: a received frame into the RX state of the device, with its time
  of reception (`k_uptime_get_32()`) for `<device>_rx_timed_out()`;
* `<device>_zephyr_send(can, &tx, frame)`: sends a frame of the device with the current values (a frame
  sent on an event);
* `<device>_zephyr_tx_start(can, &tx, hook, user_data)` and `<device>_zephyr_tx_stop()`: the TX schedule,
  one `k_work_delayable` on the system work queue per cyclic frame at the period of the map. The hook is
  called before each transmission to update the values of the frame in `tx` (it runs on the work queue: guard
  the values the application changes elsewhere).

```c
CAN_MSGQ_DEFINE(rx_queue, 8);
static bms_tx_t tx;
static bms_rx_t rx;

bms_tx_init(&tx);
bms_rx_init(&rx);
bms_zephyr_add_rx_filters(can, &rx_queue);
bms_zephyr_tx_start(can, &tx, before_send, NULL);

struct can_frame frame;
while (k_msgq_get(&rx_queue, &frame, K_FOREVER) == 0) {
    if (bms_zephyr_dispatch(&rx, &frame) == BMS_RX_VCU_COMMAND) { ... }
}
```

## The Zephyr module

This repository is a Zephyr module (`zephyr/module.yml`): add it to the west manifest of the application, or
pass it in `ZEPHYR_EXTRA_MODULES`. Set `CONFIG_MAPCAN=y` and generate the code from the map in the
application's `CMakeLists.txt`:

```cmake
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(app)
target_sources(app PRIVATE src/main.c)
mapcan_generate(MAP ../vehicle-can.yaml DEVICE bms)
```

`mapcan_generate(MAP <map> [DEVICE <name>...] [BUS <name>...] [PREFIX <prefix>] [PHYS_TYPE float|double|int]
[TARGET <target>])` runs `mapcan gen c --target zephyr` at configuration time into the build folder and adds
the code to the target (`app` by default). The map and the YAML files next to it are dependencies of the
configuration: when one changes, the build configures again and the code is generated again, so it is never
stale. The `mapcan` command must be on the build host (`pip install mapcan`), or named in
`MAPCAN_EXECUTABLE`.

[examples/zephyr](../examples/zephyr) is the battery of [examples/vehicle-can.yaml](../examples/vehicle-can.yaml)
on Zephyr; CI builds it for `native_sim` with the loopback CAN driver and runs it:

```text
west build -b native_sim/native/64 examples/zephyr -- -DZEPHYR_EXTRA_MODULES=<this repository>
```
