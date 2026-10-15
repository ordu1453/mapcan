/* A stand-in for <zephyr/drivers/can.h> in the tests of the generated Zephyr adapter: the names, values and
 * signatures of the Zephyr CAN API it uses (Zephyr 3.6 and later); can_send() and the filters only record what
 * they are given. Not Zephyr's code. */
#ifndef STUB_ZEPHYR_DRIVERS_CAN_H
#define STUB_ZEPHYR_DRIVERS_CAN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/kernel.h>

#ifdef CONFIG_CAN_FD_MODE
#define CAN_MAX_DLEN 64U
#else
#define CAN_MAX_DLEN 8U
#endif

#define CAN_STD_ID_MASK 0x7FFU
#define CAN_EXT_ID_MASK 0x1FFFFFFFU

#define CAN_FRAME_IDE (1U << 0)
#define CAN_FRAME_RTR (1U << 1)
#define CAN_FRAME_FDF (1U << 2)
#define CAN_FRAME_BRS (1U << 3)
#define CAN_FRAME_ESI (1U << 4)

#define CAN_FILTER_IDE (1U << 0)

struct device {
    const char *name;
};

struct can_frame {
    uint32_t id;
    uint8_t dlc;
    uint8_t flags;
    uint16_t reserved;
    uint8_t data[CAN_MAX_DLEN];
};

struct can_filter {
    uint32_t id;
    uint32_t mask;
    uint8_t flags;
};

typedef void (*can_tx_callback_t)(const struct device *dev, int error, void *user_data);

static inline uint8_t can_dlc_to_bytes(uint8_t dlc)
{
    static const uint8_t dlc_table[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64};
    return dlc_table[dlc & 0xFU];
}

static inline uint8_t can_bytes_to_dlc(uint8_t num_bytes)
{
    return num_bytes <= 8U ? num_bytes : num_bytes <= 12U ? 9U : num_bytes <= 16U ? 10U : num_bytes <= 20U ? 11U
         : num_bytes <= 24U ? 12U : num_bytes <= 32U ? 13U : num_bytes <= 48U ? 14U : 15U;
}

/* The stub: what was sent and which filters were added */
extern struct can_frame stub_sent[16];
extern int stub_sent_count;
extern struct can_filter stub_filters[16];
extern int stub_filter_count;

static inline int can_send(const struct device *dev, const struct can_frame *frame, k_timeout_t timeout,
                           can_tx_callback_t callback, void *user_data)
{
    (void)dev;
    (void)timeout;
    (void)callback;
    (void)user_data;
    if (stub_sent_count >= 16) {
        return -11;   /* -EAGAIN */
    }
    stub_sent[stub_sent_count++] = *frame;
    return 0;
}

static inline int can_add_rx_filter_msgq(const struct device *dev, struct k_msgq *msgq, const struct can_filter *filter)
{
    (void)dev;
    (void)msgq;
    if (stub_filter_count >= 16) {
        return -28;   /* -ENOSPC */
    }
    stub_filters[stub_filter_count] = *filter;
    return stub_filter_count++;
}

#endif
