/* The battery (bms) of examples/vehicle-can.yaml on Zephyr, with the code mapcan generates from the map:
 * it sends its frames every period of the map, receives the command of the VCU through its acceptance filters
 * and watches its receive timeout. On native_sim the CAN controller is a loopback, so the application plays the
 * VCU too and sends its command. */
#include <zephyr/device.h>
#include <zephyr/drivers/can.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "bms_zephyr.h"

CAN_MSGQ_DEFINE(rx_queue, 8);

static bms_tx_t tx;
static bms_rx_t rx;

/* Called before each cyclic transmission: the values to send */
static void before_send(bms_tx_frame_t frame, bms_tx_t *values, void *user_data)
{
    (void)user_data;
    if (frame == BMS_TX_BMS_STATUS) {
        values->bms_status.pack_voltage = 398.5f;
        values->bms_status.pack_current = -12.0f;
    }
}

int main(void)
{
    const struct device *can = DEVICE_DT_GET(DT_CHOSEN(zephyr_canbus));

    /* The loopback: the frames sent come back to the acceptance filters */
    if (!device_is_ready(can) || can_set_mode(can, CAN_MODE_LOOPBACK) != 0 || can_start(can) != 0) {
        printk("CAN controller not ready\n");
        return 0;
    }
    bms_tx_init(&tx);
    bms_rx_init(&rx);
    if (bms_zephyr_add_rx_filters(can, &rx_queue) != 0 || bms_zephyr_tx_start(can, &tx, before_send, NULL) != 0) {
        printk("cannot set up the bms\n");
        return 0;
    }

    /* The VCU: a contactor request with a torque request of 120.5 N·m (raw 1205, little-endian) */
    struct can_frame command = {.id = VCU_COMMAND_ID, .dlc = can_bytes_to_dlc(VCU_COMMAND_LENGTH)};
    command.data[0] = VCU_COMMAND_CONTACTOR_REQUEST_CLOSE;
    command.data[1] = 1205 & 0xFF;
    command.data[2] = 1205 >> 8;
    (void)can_send(can, &command, K_MSEC(100), NULL, NULL);

    struct can_frame frame;
    while (k_msgq_get(&rx_queue, &frame, K_MSEC(200)) == 0) {
        if (bms_zephyr_dispatch(&rx, &frame) == BMS_RX_VCU_COMMAND) {
            printk("bms: contactor request %u, torque request %d (raw)\n",
                   (unsigned int)rx.vcu_command.contactor_request, (int)rx.vcu_command.torque_request);
        }
    }
    /* No command for longer than its timeout (three periods of 20 ms): a real bms opens the contactors */
    k_sleep(K_MSEC(100));
    printk("bms: command timed out: %s\n",
           bms_rx_timed_out(&rx, BMS_RX_VCU_COMMAND, k_uptime_get_32()) ? "yes" : "no");
    bms_zephyr_tx_stop();
    return 0;
}
