/* A stand-in for <zephyr/kernel.h> in the tests of the generated Zephyr adapter: the names and signatures of the
 * Zephyr API it uses (Zephyr 3.6 and later), with work items the test runs by hand. Not Zephyr's code. */
#ifndef STUB_ZEPHYR_KERNEL_H
#define STUB_ZEPHYR_KERNEL_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int64_t ms;
} k_timeout_t;

#define K_MSEC(ms) ((k_timeout_t){(int64_t)(ms)})
#define K_NO_WAIT ((k_timeout_t){0})

#define CONTAINER_OF(ptr, type, field) ((type *)(void *)(((char *)(ptr)) - offsetof(type, field)))

struct k_work;
typedef void (*k_work_handler_t)(struct k_work *work);

struct k_work {
    k_work_handler_t handler;
};

struct k_work_delayable {
    struct k_work work;
    int scheduled;      /* the stub: scheduled and not run yet */
    int64_t delay_ms;   /* the stub: the delay of the last (re)schedule */
};

struct k_msgq {
    int unused;
};

static inline void k_work_init_delayable(struct k_work_delayable *dwork, k_work_handler_t handler)
{
    dwork->work.handler = handler;
    dwork->scheduled = 0;
    dwork->delay_ms = -1;
}

/* The stub: the work items ever scheduled, for the test to run */
extern struct k_work_delayable *stub_works[16];
extern int stub_work_count;

static inline int k_work_schedule(struct k_work_delayable *dwork, k_timeout_t delay)
{
    int known = 0;
    for (int i = 0; i < stub_work_count; i++) {
        known |= stub_works[i] == dwork;
    }
    if (!known && stub_work_count < 16) {
        stub_works[stub_work_count++] = dwork;
    }
    dwork->scheduled = 1;
    dwork->delay_ms = delay.ms;
    return 1;
}

static inline int k_work_reschedule(struct k_work_delayable *dwork, k_timeout_t delay)
{
    return k_work_schedule(dwork, delay);
}

static inline int k_work_cancel_delayable(struct k_work_delayable *dwork)
{
    dwork->scheduled = 0;
    return 0;
}

static inline struct k_work_delayable *k_work_delayable_from_work(struct k_work *work)
{
    return CONTAINER_OF(work, struct k_work_delayable, work);
}

/* The stub: the time the test sets */
extern uint32_t stub_uptime_ms;

static inline uint32_t k_uptime_get_32(void)
{
    return stub_uptime_ms;
}

#endif
