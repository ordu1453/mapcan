/* bus1.h — сгенерировано mapcan из карты «Эталонная карта CANopen»
 * версии 1.0.0. Не редактируйте вручную: источник — YAML-карта. */
#ifndef BUS1_MAPCAN_H
#define BUS1_MAPCAN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef MAPCAN_BITS_HELPERS
#define MAPCAN_BITS_HELPERS 0xABE369DBu
/* Нумерация бит lsb0: бит p — бит (p % 8) байта (p / 8); start — позиция LSB.
 * big-endian (Motorola): после старшего бита байта цепочка продолжается
 * с бита 0 предыдущего байта. */
static inline uint64_t mapcan_get_bits(const uint8_t *data, uint16_t start, uint8_t length, bool big_endian)
{
    uint64_t value = 0u;
    uint8_t done = 0u;
    int16_t pos = (int16_t)start;
    while (done < length) {
        uint8_t byte = (uint8_t)(pos / 8);
        uint8_t shift = (uint8_t)(pos % 8);
        uint8_t n = (uint8_t)(8u - shift);
        if (n > (uint8_t)(length - done)) {
            n = (uint8_t)(length - done);
        }
        uint8_t chunk = (uint8_t)((data[byte] >> shift) & (uint8_t)((1u << n) - 1u));
        value |= (uint64_t)chunk << done;
        done = (uint8_t)(done + n);
        pos = big_endian ? (int16_t)((byte - 1) * 8) : (int16_t)((byte + 1) * 8);
    }
    return value;
}

static inline void mapcan_set_bits(uint8_t *data, uint64_t value, uint16_t start, uint8_t length, bool big_endian)
{
    uint8_t done = 0u;
    int16_t pos = (int16_t)start;
    while (done < length) {
        uint8_t byte = (uint8_t)(pos / 8);
        uint8_t shift = (uint8_t)(pos % 8);
        uint8_t n = (uint8_t)(8u - shift);
        if (n > (uint8_t)(length - done)) {
            n = (uint8_t)(length - done);
        }
        uint8_t mask = (uint8_t)(((1u << n) - 1u) << shift);
        uint8_t chunk = (uint8_t)(((value >> done) << shift) & mask);
        data[byte] = (uint8_t)((data[byte] & (uint8_t)~mask) | chunk);
        done = (uint8_t)(done + n);
        pos = big_endian ? (int16_t)((byte - 1) * 8) : (int16_t)((byte + 1) * 8);
    }
}

/* Значение вне диапазона поля прижимается к границе, а не обрезается до младших бит. */
static inline uint64_t mapcan_clamp_u(uint64_t value, uint64_t hi)
{
    return value > hi ? hi : value;
}
static inline int64_t mapcan_clamp_s(int64_t value, int64_t lo, int64_t hi)
{
    return value < lo ? lo : (value > hi ? hi : value);
}

static inline int64_t mapcan_sign_extend(uint64_t value, uint8_t length)
{
    uint64_t sign = (uint64_t)1u << (length - 1u);
    return (int64_t)((value ^ sign) - sign);
}
static inline int32_t mapcan_sign_extend32(uint32_t value, uint8_t length)
{
    uint32_t sign = (uint32_t)1u << (length - 1u);
    return (int32_t)((value ^ sign) - sign);
}

/* Обратный код (representation: ones_complement): отрицательное — инверсия модуля. */
static inline int64_t mapcan_ones_decode(uint64_t value, uint8_t length)
{
    uint64_t sign = (uint64_t)1u << (length - 1u);
    return (value & sign) ? -(int64_t)(~value & (sign - 1u)) : (int64_t)value;
}
static inline uint64_t mapcan_ones_encode(int64_t value)
{
    return value < 0 ? ~(uint64_t)(-value) : (uint64_t)value;
}

/* Прямой код (representation: sign_magnitude): старший бит — знак, остальные — модуль. */
static inline int64_t mapcan_sm_decode(uint64_t value, uint8_t length)
{
    uint64_t sign = (uint64_t)1u << (length - 1u);
    return (value & sign) ? -(int64_t)(value & (sign - 1u)) : (int64_t)value;
}
static inline uint64_t mapcan_sm_encode(int64_t value, uint8_t length)
{
    return value < 0 ? (((uint64_t)1u << (length - 1u)) | (uint64_t)(-value)) : (uint64_t)value;
}

/* IEEE 754: float/double <-> сырые биты (через memcpy: корректно и в C, и в C++). */
static inline uint32_t mapcan_f32_to_bits(float f)
{
    uint32_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}
static inline float mapcan_bits_to_f32(uint32_t u)
{
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}
static inline uint64_t mapcan_f64_to_bits(double f)
{
    uint64_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}
static inline double mapcan_bits_to_f64(uint64_t u)
{
    double f;
    memcpy(&f, &u, sizeof f);
    return f;
}

static inline float mapcan_round_f(float x)
{
    return (x >= 0.0f) ? (x + 0.5f) : (x - 0.5f);
}

static inline double mapcan_round_d(double x)
{
    return (x >= 0.0) ? (x + 0.5) : (x - 0.5);
}

/* Таблицы устройства (mapcan gen c --device): расписание передачи (cycle_ms 0 — не
 * циклически, inhibit_us 0 — без минимального интервала), принимаемые кадры (timeout_ms 0 —
 * без тайм-аута) и фильтры приёма (ID/маска). */
typedef struct {
    uint32_t id;
    uint16_t length;
    bool extended;
    bool fd;
    uint32_t cycle_ms;
    bool on_event;
    uint32_t inhibit_us;
} mapcan_tx_entry_t;
typedef struct {
    uint32_t id;
    uint16_t length;
    bool extended;
    bool fd;
    uint32_t cycle_ms;
    uint32_t timeout_ms;
} mapcan_rx_entry_t;
typedef struct {
    uint32_t id;
    uint32_t mask;
    bool extended;
} mapcan_filter_t;
#elif MAPCAN_BITS_HELPERS != 0xABE369DBu
#error "mapcan: заголовки сгенерированы разными версиями mapcan, перегенерируйте их вместе"
#endif /* MAPCAN_BITS_HELPERS */

#define BUS1_MAP_VERSION_MAJOR 1u
#define BUS1_MAP_VERSION_MINOR 0u
#define BUS1_MAP_VERSION_PATCH 0u
#define BUS1_MAP_LAYOUT_CRC32 0x32019DD4u
#ifndef MAPCAN_NO_DEPRECATED
#define MAP_VERSION_MAJOR 1u /* устарело: используйте BUS1_MAP_VERSION_MAJOR */
#define MAP_VERSION_MINOR 0u /* устарело: используйте BUS1_MAP_VERSION_MINOR */
#define MAP_VERSION_PATCH 0u /* устарело: используйте BUS1_MAP_VERSION_PATCH */
#define MAP_LAYOUT_CRC32 0x32019DD4u /* устарело: используйте BUS1_MAP_LAYOUT_CRC32 */
#endif
#define BUS1_BITRATE 500000u
#define IMD_NODE_ID 0x21u
#define CMU_NODE_ID 0x22u
#define PCU_NODE_ID 0x23u
#define BYPASS_NODE_ID 0x24u
#define COOLING_NODE_ID 0x25u

/* ------------------------------------------------------------------------ */
/* sync: Синхронизация со всеми устройствами */
#define SYNC_ID 0x080u
#define SYNC_LENGTH 0u
#define SYNC_DLC SYNC_LENGTH /* устарело: используйте SYNC_LENGTH */

typedef struct {
    uint8_t reserved_; /* сигналы не описаны */
} sync_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void sync_init(sync_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int sync_pack(uint8_t *data, size_t size, const sync_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int sync_unpack(sync_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* time_stamp: Дата и время */
#define TIME_STAMP_ID 0x100u
#define TIME_STAMP_LENGTH 6u
#define TIME_STAMP_DLC TIME_STAMP_LENGTH /* устарело: используйте TIME_STAMP_LENGTH */

#define TIME_STAMP_MS_AFTER_MIDNIGHT_FACTOR (1.0)
#define TIME_STAMP_MS_AFTER_MIDNIGHT_OFFSET (0.0)
/* ms_after_midnight: единица измерения — мс */
static inline double time_stamp_ms_after_midnight_to_phys(uint32_t raw)
{
    return (double)raw * TIME_STAMP_MS_AFTER_MIDNIGHT_FACTOR + TIME_STAMP_MS_AFTER_MIDNIGHT_OFFSET;
}
static inline uint32_t time_stamp_ms_after_midnight_from_phys(double phys)
{
    double r = mapcan_round_d((phys - TIME_STAMP_MS_AFTER_MIDNIGHT_OFFSET) / TIME_STAMP_MS_AFTER_MIDNIGHT_FACTOR);
    if (r < 0.0) { return 0u; }
    if (r >= 268435456.0) { return 268435455u; }
    return (uint32_t)r;
}

#define TIME_STAMP_DAYS_SINCE_1984_FACTOR (1.0f)
#define TIME_STAMP_DAYS_SINCE_1984_OFFSET (0.0f)
/* days_since_1984: единица измерения — сут */
static inline float time_stamp_days_since_1984_to_phys(uint16_t raw)
{
    return (float)raw * TIME_STAMP_DAYS_SINCE_1984_FACTOR + TIME_STAMP_DAYS_SINCE_1984_OFFSET;
}
static inline uint16_t time_stamp_days_since_1984_from_phys(float phys)
{
    float r = mapcan_round_f((phys - TIME_STAMP_DAYS_SINCE_1984_OFFSET) / TIME_STAMP_DAYS_SINCE_1984_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

typedef struct {
    uint32_t ms_after_midnight; /* Миллисекунды с начала суток [мс] */
    uint16_t days_since_1984; /* Дни с 1 января 1984 г. [сут] */
} time_stamp_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void time_stamp_init(time_stamp_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int time_stamp_pack(uint8_t *data, size_t size, const time_stamp_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int time_stamp_unpack(time_stamp_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* imd_state: Состояние изоляции */
#define IMD_STATE_ID 0x1A1u
#define IMD_STATE_LENGTH 3u
#define IMD_STATE_DLC IMD_STATE_LENGTH /* устарело: используйте IMD_STATE_LENGTH */
#define IMD_STATE_CYCLE_MS 100u

/* insulation_status: Статус изоляции */
typedef enum {
    IMD_STATE_INSULATION_STATUS_NO_DATA = 0, /* нет данных о сопротивлении изоляции */
    IMD_STATE_INSULATION_STATUS_OK = 1, /* сопротивление изоляции в норме */
    IMD_STATE_INSULATION_STATUS_WARNING = 2, /* низкое сопротивление изоляции: меньше WARNING_RESISTANCE, но больше ALARM_RESISTANCE */
    IMD_STATE_INSULATION_STATUS_ALARM = 3, /* аварийно-низкое сопротивление изоляции, меньше ALARM_RESISTANCE */
} imd_state_insulation_status_t;

#define IMD_STATE_INTERNAL_ERROR_LOW_BUS_VOLTAGE_ERROR_SHIFT 0u
#define IMD_STATE_INTERNAL_ERROR_LOW_BUS_VOLTAGE_ERROR_MASK 0x1u /* низкое напряжение шины */
#define IMD_STATE_INTERNAL_ERROR_TIMEOUT_ERROR_SHIFT 1u
#define IMD_STATE_INTERNAL_ERROR_TIMEOUT_ERROR_MASK 0x2u /* тайм-аут измерения */
#define IMD_STATE_INTERNAL_ERROR_ANOMALY_ERROR_SHIFT 2u
#define IMD_STATE_INTERNAL_ERROR_ANOMALY_ERROR_MASK 0x4u /* аномальное состояние между шинами питания и корпусом — может указывать на периодический контакт шины с корпусом */
#define IMD_STATE_INTERNAL_ERROR_SELF_TEST_ERROR_SHIFT 3u
#define IMD_STATE_INTERNAL_ERROR_SELF_TEST_ERROR_MASK 0x8u /* ошибка самопроверки */

/* imd_state: Состояние работы */
typedef enum {
    IMD_STATE_IMD_STATE_NOT_WORKING = 0, /* устройство не работает */
    IMD_STATE_IMD_STATE_WORKING = 1, /* устройство работает */
    IMD_STATE_IMD_STATE_CRITICAL_FAULT = 2, /* критический сбой в работе устройства */
} imd_state_imd_state_t;

typedef struct {
    uint8_t insulation_status; /* Статус изоляции */
    uint8_t internal_error; /* Статус внутренней ошибки */
    uint8_t imd_state; /* Состояние работы */
} imd_state_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void imd_state_init(imd_state_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int imd_state_pack(uint8_t *data, size_t size, const imd_state_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int imd_state_unpack(imd_state_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* imd_data: Данные по изоляции */
#define IMD_DATA_ID 0x2A1u
#define IMD_DATA_LENGTH 8u
#define IMD_DATA_DLC IMD_DATA_LENGTH /* устарело: используйте IMD_DATA_LENGTH */
#define IMD_DATA_CYCLE_MS 100u

/* resistance_calculated: Флаг расчёта сопротивления изоляции */
typedef enum {
    IMD_DATA_RESISTANCE_CALCULATED_NOT_CALCULATED = 0, /* значения сопротивлений изоляции не рассчитаны */
    IMD_DATA_RESISTANCE_CALCULATED_CALCULATED = 1, /* значения сопротивлений изоляции рассчитаны */
} imd_data_resistance_calculated_t;

#define IMD_DATA_RESISTANCE_PLUS_FACTOR (1.0f)
#define IMD_DATA_RESISTANCE_PLUS_OFFSET (0.0f)
/* resistance_plus: единица измерения — кОм */
static inline float imd_data_resistance_plus_to_phys(uint16_t raw)
{
    return (float)raw * IMD_DATA_RESISTANCE_PLUS_FACTOR + IMD_DATA_RESISTANCE_PLUS_OFFSET;
}
static inline uint16_t imd_data_resistance_plus_from_phys(float phys)
{
    float r = mapcan_round_f((phys - IMD_DATA_RESISTANCE_PLUS_OFFSET) / IMD_DATA_RESISTANCE_PLUS_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

#define IMD_DATA_RESISTANCE_MINUS_FACTOR (1.0f)
#define IMD_DATA_RESISTANCE_MINUS_OFFSET (0.0f)
/* resistance_minus: единица измерения — кОм */
static inline float imd_data_resistance_minus_to_phys(uint16_t raw)
{
    return (float)raw * IMD_DATA_RESISTANCE_MINUS_FACTOR + IMD_DATA_RESISTANCE_MINUS_OFFSET;
}
static inline uint16_t imd_data_resistance_minus_from_phys(float phys)
{
    float r = mapcan_round_f((phys - IMD_DATA_RESISTANCE_MINUS_OFFSET) / IMD_DATA_RESISTANCE_MINUS_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

/* bus_voltage_calculated: Флаг расчёта напряжения шины питания */
typedef enum {
    IMD_DATA_BUS_VOLTAGE_CALCULATED_NOT_CALCULATED = 0, /* значение напряжения не рассчитано */
    IMD_DATA_BUS_VOLTAGE_CALCULATED_CALCULATED = 1, /* значение напряжения рассчитано */
} imd_data_bus_voltage_calculated_t;

#define IMD_DATA_BUS_VOLTAGE_FACTOR (0.1f)
#define IMD_DATA_BUS_VOLTAGE_OFFSET (0.0f)
/* bus_voltage: единица измерения — В */
static inline float imd_data_bus_voltage_to_phys(uint16_t raw)
{
    return (float)raw * IMD_DATA_BUS_VOLTAGE_FACTOR + IMD_DATA_BUS_VOLTAGE_OFFSET;
}
static inline uint16_t imd_data_bus_voltage_from_phys(float phys)
{
    float r = mapcan_round_f((phys - IMD_DATA_BUS_VOLTAGE_OFFSET) / IMD_DATA_BUS_VOLTAGE_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

typedef struct {
    uint8_t resistance_calculated; /* Флаг расчёта сопротивления изоляции */
    uint16_t resistance_plus; /* Изоляция между «плюсом» шины питания и корпусом [кОм] */
    uint16_t resistance_minus; /* Изоляция между «минусом» шины питания и корпусом [кОм] */
    uint8_t bus_voltage_calculated; /* Флаг расчёта напряжения шины питания */
    uint16_t bus_voltage; /* Напряжение шины питания [В] */
} imd_data_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void imd_data_init(imd_data_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int imd_data_pack(uint8_t *data, size_t size, const imd_data_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int imd_data_unpack(imd_data_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* imd_command: Команды монитору изоляции */
#define IMD_COMMAND_ID 0x221u
#define IMD_COMMAND_LENGTH 2u
#define IMD_COMMAND_DLC IMD_COMMAND_LENGTH /* устарело: используйте IMD_COMMAND_LENGTH */
#define IMD_COMMAND_CYCLE_MS 100u

/* allow_work: Команда разрешения работы устройства */
typedef enum {
    IMD_COMMAND_ALLOW_WORK_FORBID = 0, /* запрет работы */
    IMD_COMMAND_ALLOW_WORK_ALLOW = 1, /* разрешение работы */
} imd_command_allow_work_t;

/* force_selftest: Команда принудительной самодиагностики */
typedef enum {
    IMD_COMMAND_FORCE_SELFTEST_AUTO = 0, /* запуск самодиагностики по внутреннему алгоритму */
    IMD_COMMAND_FORCE_SELFTEST_FORCE = 1, /* принудительный запуск самодиагностики (если активно, выполняется только самодиагностика) */
} imd_command_force_selftest_t;

typedef struct {
    uint8_t allow_work; /* Команда разрешения работы устройства */
    uint8_t force_selftest; /* Команда принудительной самодиагностики */
} imd_command_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void imd_command_init(imd_command_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int imd_command_pack(uint8_t *data, size_t size, const imd_command_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int imd_command_unpack(imd_command_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* imd_sdo_request: Настройка граничных значений */
#define IMD_SDO_REQUEST_ID 0x621u
#define IMD_SDO_REQUEST_LENGTH 8u
#define IMD_SDO_REQUEST_DLC IMD_SDO_REQUEST_LENGTH /* устарело: используйте IMD_SDO_REQUEST_LENGTH */

/* sdo_command: Команда SDO */
typedef enum {
    IMD_SDO_REQUEST_SDO_COMMAND_WRITE_2_BYTES = 43,
} imd_sdo_request_sdo_command_t;

/* sdo_index: Индекс объекта */
typedef enum {
    IMD_SDO_REQUEST_SDO_INDEX_INDEX_4010 = 16400,
} imd_sdo_request_sdo_index_t;

/* sdo_subindex: Субиндекс объекта */
typedef enum {
    IMD_SDO_REQUEST_SDO_SUBINDEX_SET_ALARM_RESISTANCE = 1, /* Установка ALARM_RESISTANCE */
    IMD_SDO_REQUEST_SDO_SUBINDEX_SET_WARNING_RESISTANCE = 2, /* Установка WARNING_RESISTANCE */
} imd_sdo_request_sdo_subindex_t;

#define IMD_SDO_REQUEST_ALARM_RESISTANCE_FACTOR (1.0f)
#define IMD_SDO_REQUEST_ALARM_RESISTANCE_OFFSET (0.0f)
/* alarm_resistance: единица измерения — кОм */
static inline float imd_sdo_request_alarm_resistance_to_phys(uint16_t raw)
{
    return (float)raw * IMD_SDO_REQUEST_ALARM_RESISTANCE_FACTOR + IMD_SDO_REQUEST_ALARM_RESISTANCE_OFFSET;
}
static inline uint16_t imd_sdo_request_alarm_resistance_from_phys(float phys)
{
    float r = mapcan_round_f((phys - IMD_SDO_REQUEST_ALARM_RESISTANCE_OFFSET) / IMD_SDO_REQUEST_ALARM_RESISTANCE_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

#define IMD_SDO_REQUEST_WARNING_RESISTANCE_FACTOR (1.0f)
#define IMD_SDO_REQUEST_WARNING_RESISTANCE_OFFSET (0.0f)
/* warning_resistance: единица измерения — кОм */
static inline float imd_sdo_request_warning_resistance_to_phys(uint16_t raw)
{
    return (float)raw * IMD_SDO_REQUEST_WARNING_RESISTANCE_FACTOR + IMD_SDO_REQUEST_WARNING_RESISTANCE_OFFSET;
}
static inline uint16_t imd_sdo_request_warning_resistance_from_phys(float phys)
{
    float r = mapcan_round_f((phys - IMD_SDO_REQUEST_WARNING_RESISTANCE_OFFSET) / IMD_SDO_REQUEST_WARNING_RESISTANCE_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

typedef struct {
    uint8_t sdo_command; /* Команда SDO */
    uint16_t sdo_index; /* Индекс объекта */
    uint8_t sdo_subindex; /* Субиндекс объекта */
    uint16_t alarm_resistance; /* Порог аварийного сопротивления изоляции [кОм] */
    uint16_t warning_resistance; /* Порог предупредительного сопротивления изоляции [кОм] */
} imd_sdo_request_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void imd_sdo_request_init(imd_sdo_request_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int imd_sdo_request_pack(uint8_t *data, size_t size, const imd_sdo_request_t *msg);
/* Распаковать: сигналы другого значения селектора получают начальные значения; возвращает 0 или -1, если данных меньше длины кадра. */
int imd_sdo_request_unpack(imd_sdo_request_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* imd_sdo_response: Обратная связь по принятой настройке */
#define IMD_SDO_RESPONSE_ID 0x5A1u
#define IMD_SDO_RESPONSE_LENGTH 8u
#define IMD_SDO_RESPONSE_DLC IMD_SDO_RESPONSE_LENGTH /* устарело: используйте IMD_SDO_RESPONSE_LENGTH */

/* sdo_command: Команда SDO */
typedef enum {
    IMD_SDO_RESPONSE_SDO_COMMAND_WRITE_OK = 96,
} imd_sdo_response_sdo_command_t;

/* sdo_index: Индекс объекта */
typedef enum {
    IMD_SDO_RESPONSE_SDO_INDEX_INDEX_4010 = 16400,
} imd_sdo_response_sdo_index_t;

/* sdo_subindex: Субиндекс объекта */
typedef enum {
    IMD_SDO_RESPONSE_SDO_SUBINDEX_ACK_ALARM_RESISTANCE = 1, /* Принят ALARM_RESISTANCE */
    IMD_SDO_RESPONSE_SDO_SUBINDEX_ACK_WARNING_RESISTANCE = 2, /* Принят WARNING_RESISTANCE */
} imd_sdo_response_sdo_subindex_t;

typedef struct {
    uint8_t sdo_command; /* Команда SDO */
    uint16_t sdo_index; /* Индекс объекта */
    uint8_t sdo_subindex; /* Субиндекс объекта */
} imd_sdo_response_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void imd_sdo_response_init(imd_sdo_response_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int imd_sdo_response_pack(uint8_t *data, size_t size, const imd_sdo_response_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int imd_sdo_response_unpack(imd_sdo_response_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* cmu_state: Состояние ячеек */
#define CMU_STATE_ID 0x1A2u
#define CMU_STATE_LENGTH 2u
#define CMU_STATE_DLC CMU_STATE_LENGTH /* устарело: используйте CMU_STATE_LENGTH */
#define CMU_STATE_CYCLE_MS 50u

/* cmu_status: Состояние работы устройства */
typedef enum {
    CMU_STATE_CMU_STATUS_NO_DATA = 0,
    CMU_STATE_CMU_STATUS_OK = 1,
    CMU_STATE_CMU_STATUS_WARNING = 2,
    CMU_STATE_CMU_STATUS_ALARM = 3,
} cmu_state_cmu_status_t;

#define CMU_STATE_SYSTEMS_STATUS_CELL_OVERVOLTAGE_SHIFT 0u
#define CMU_STATE_SYSTEMS_STATUS_CELL_OVERVOLTAGE_MASK 0x1u /* высокое напряжение на ячейке */
#define CMU_STATE_SYSTEMS_STATUS_CELL_UNDERVOLTAGE_SHIFT 1u
#define CMU_STATE_SYSTEMS_STATUS_CELL_UNDERVOLTAGE_MASK 0x2u /* низкое напряжение на ячейке */
#define CMU_STATE_SYSTEMS_STATUS_CELL_DISBALANCE_SHIFT 2u
#define CMU_STATE_SYSTEMS_STATUS_CELL_DISBALANCE_MASK 0x4u /* разбалансировка ячеек */
#define CMU_STATE_SYSTEMS_STATUS_VOLTAGE_SENSOR_LOST_SHIFT 3u
#define CMU_STATE_SYSTEMS_STATUS_VOLTAGE_SENSOR_LOST_MASK 0x8u /* нет связи с модулем измерения напряжения */
#define CMU_STATE_SYSTEMS_STATUS_CELL_OVERHEAT_SHIFT 4u
#define CMU_STATE_SYSTEMS_STATUS_CELL_OVERHEAT_MASK 0x10u /* перегрев ячеек */
#define CMU_STATE_SYSTEMS_STATUS_CELL_OVERCOOLING_SHIFT 5u
#define CMU_STATE_SYSTEMS_STATUS_CELL_OVERCOOLING_MASK 0x20u /* переохлаждение ячеек */
#define CMU_STATE_SYSTEMS_STATUS_TEMPERATURE_SENSOR_LOST_SHIFT 6u
#define CMU_STATE_SYSTEMS_STATUS_TEMPERATURE_SENSOR_LOST_MASK 0x40u /* нет связи с датчиком температуры */

typedef struct {
    uint8_t cmu_status; /* Состояние работы устройства */
    uint8_t systems_status; /* Код состояния систем */
} cmu_state_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void cmu_state_init(cmu_state_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int cmu_state_pack(uint8_t *data, size_t size, const cmu_state_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int cmu_state_unpack(cmu_state_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* cmu_event: Изменение состояния */
#define CMU_EVENT_ID 0x0A2u
#define CMU_EVENT_LENGTH 3u
#define CMU_EVENT_DLC CMU_EVENT_LENGTH /* устарело: используйте CMU_EVENT_LENGTH */

/* event_type: Код события */
typedef enum {
    CMU_EVENT_EVENT_TYPE_CELL_OVERVOLTAGE = 1, /* высокое напряжение на ячейке */
    CMU_EVENT_EVENT_TYPE_CELL_UNDERVOLTAGE = 2, /* низкое напряжение на ячейке */
    CMU_EVENT_EVENT_TYPE_CELL_DISBALANCE = 3, /* разбалансировка ячеек */
    CMU_EVENT_EVENT_TYPE_VOLTAGE_SENSOR_LOST = 4, /* нет связи с модулем измерения напряжения */
    CMU_EVENT_EVENT_TYPE_CELL_OVERHEAT = 5, /* перегрев ячеек */
    CMU_EVENT_EVENT_TYPE_CELL_OVERCOOLING = 6, /* переохлаждение ячеек */
    CMU_EVENT_EVENT_TYPE_TEMPERATURE_SENSOR_LOST = 7, /* нет связи с датчиком температуры */
} cmu_event_event_type_t;

/* event_source: Источник события */
typedef enum {
    CMU_EVENT_EVENT_SOURCE_VOLTAGE_MODULES = 0, /* модули напряжения */
    CMU_EVENT_EVENT_SOURCE_TEMPERATURE_SENSORS = 1, /* датчики температур */
} cmu_event_event_source_t;

typedef struct {
    uint8_t event_type; /* Код события */
    uint8_t event_source; /* Источник события */
    uint8_t event_object; /* Объект события — номер модуля или датчика */
} cmu_event_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void cmu_event_init(cmu_event_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int cmu_event_pack(uint8_t *data, size_t size, const cmu_event_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int cmu_event_unpack(cmu_event_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* cmu_parse_data: Парсинг данных (по запросу) */
#define CMU_PARSE_DATA_ID 0x2A2u
#define CMU_PARSE_DATA_LENGTH 8u
#define CMU_PARSE_DATA_DLC CMU_PARSE_DATA_LENGTH /* устарело: используйте CMU_PARSE_DATA_LENGTH */

/* parse_type: Тип парсинга (селектор мультиплексора) */
typedef enum {
    CMU_PARSE_DATA_PARSE_TYPE_VOLTAGES = 0, /* парсинг напряжений */
    CMU_PARSE_DATA_PARSE_TYPE_TEMPERATURES = 1, /* парсинг температур */
} cmu_parse_data_parse_type_t;

typedef struct {
    uint8_t parse_type; /* Тип парсинга (селектор мультиплексора) */
    uint8_t parse_index; /* Номер кадра парсинга */
    uint8_t voltage_data[7]; /* Данные парсинга напряжений */
    uint8_t temperature_data[7]; /* Данные парсинга температур */
} cmu_parse_data_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void cmu_parse_data_init(cmu_parse_data_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int cmu_parse_data_pack(uint8_t *data, size_t size, const cmu_parse_data_t *msg);
/* Распаковать: сигналы другого значения селектора получают начальные значения; возвращает 0 или -1, если данных меньше длины кадра. */
int cmu_parse_data_unpack(cmu_parse_data_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* cmu_request: Объём передаваемых данных */
#define CMU_REQUEST_ID 0x222u
#define CMU_REQUEST_LENGTH 2u
#define CMU_REQUEST_DLC CMU_REQUEST_LENGTH /* устарело: используйте CMU_REQUEST_LENGTH */

/* data_request: Запрос на отправку данных */
typedef enum {
    CMU_REQUEST_DATA_REQUEST_STATES = 0, /* запрос на отправку состояний */
    CMU_REQUEST_DATA_REQUEST_FULL_PARSE = 1, /* запрос на полный парсинг данных */
    CMU_REQUEST_DATA_REQUEST_REPEAT_VOLTAGE_FRAME = 2, /* повтор определённого кадра парсинга напряжения */
    CMU_REQUEST_DATA_REQUEST_REPEAT_TEMPERATURE_FRAME = 3, /* повтор определённого кадра парсинга температуры */
} cmu_request_data_request_t;

typedef struct {
    uint8_t data_request; /* Запрос на отправку данных */
    uint8_t frame_request; /* Номер повторно запрашиваемого кадра */
} cmu_request_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void cmu_request_init(cmu_request_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int cmu_request_pack(uint8_t *data, size_t size, const cmu_request_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int cmu_request_unpack(cmu_request_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* pcu_state: Состояние преобразователя */
#define PCU_STATE_ID 0x1A3u
#define PCU_STATE_LENGTH 2u
#define PCU_STATE_DLC PCU_STATE_LENGTH /* устарело: используйте PCU_STATE_LENGTH */
#define PCU_STATE_CYCLE_MS 100u

/* dc_state: Состояние работы */
typedef enum {
    PCU_STATE_DC_STATE_STATE_INIT = 0, /* исходное состояние преобразователя */
    PCU_STATE_DC_STATE_STATE_PRECHARGE = 1, /* предзаряд входного конденсатора */
    PCU_STATE_DC_STATE_STATE_IDLE = 2, /* ключи закрыты, входной конденсатор предзаряжен, ошибок нет; ожидается команда заряда/разряда */
    PCU_STATE_DC_STATE_STATE_CHARGE = 3, /* заряд батареи */
    PCU_STATE_DC_STATE_STATE_DISCHARGE = 4, /* разряд батареи */
    PCU_STATE_DC_STATE_STATE_DIRECT_CHARGE = 5, /* батарея напрямую подключена к источнику для заряда */
    PCU_STATE_DC_STATE_STATE_DIRECT_DISCHARGE = 6, /* батарея напрямую подключена к нагрузке */
} pcu_state_dc_state_t;

#define PCU_STATE_ERROR_CODE_ERR_NONE_SHIFT 0u
#define PCU_STATE_ERROR_CODE_ERR_NONE_MASK 0x1u /* ошибок не обнаружено */
#define PCU_STATE_ERROR_CODE_ERR_OVERVOLTAGE_SHIFT 1u
#define PCU_STATE_ERROR_CODE_ERR_OVERVOLTAGE_MASK 0x2u /* превышение напряжения */
#define PCU_STATE_ERROR_CODE_ERR_UNDERVOLTAGE_SHIFT 2u
#define PCU_STATE_ERROR_CODE_ERR_UNDERVOLTAGE_MASK 0x4u /* недопустимо малое напряжение */
#define PCU_STATE_ERROR_CODE_ERR_OVERCURRENT_SHIFT 3u
#define PCU_STATE_ERROR_CODE_ERR_OVERCURRENT_MASK 0x8u /* превышение тока */
#define PCU_STATE_ERROR_CODE_ERR_IGBT_DRIVER_SHIFT 4u
#define PCU_STATE_ERROR_CODE_ERR_IGBT_DRIVER_MASK 0x10u /* ошибка драйверов силовых ключей */

typedef struct {
    uint8_t dc_state; /* Состояние работы */
    uint8_t error_code; /* Код ошибки преобразователя */
} pcu_state_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void pcu_state_init(pcu_state_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int pcu_state_pack(uint8_t *data, size_t size, const pcu_state_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int pcu_state_unpack(pcu_state_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* pcu_data: Данные о работе */
#define PCU_DATA_ID 0x2A3u
#define PCU_DATA_LENGTH 8u
#define PCU_DATA_DLC PCU_DATA_LENGTH /* устарело: используйте PCU_DATA_LENGTH */
#define PCU_DATA_CYCLE_MS 100u

#define PCU_DATA_DC_OUTPUT_VOLTAGE_FACTOR (10.0f)
#define PCU_DATA_DC_OUTPUT_VOLTAGE_OFFSET (0.0f)
/* dc_output_voltage: единица измерения — В */
static inline float pcu_data_dc_output_voltage_to_phys(uint16_t raw)
{
    return (float)raw * PCU_DATA_DC_OUTPUT_VOLTAGE_FACTOR + PCU_DATA_DC_OUTPUT_VOLTAGE_OFFSET;
}
static inline uint16_t pcu_data_dc_output_voltage_from_phys(float phys)
{
    float r = mapcan_round_f((phys - PCU_DATA_DC_OUTPUT_VOLTAGE_OFFSET) / PCU_DATA_DC_OUTPUT_VOLTAGE_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

#define PCU_DATA_DC_INPUT_VOLTAGE_FACTOR (10.0f)
#define PCU_DATA_DC_INPUT_VOLTAGE_OFFSET (0.0f)
/* dc_input_voltage: единица измерения — В */
static inline float pcu_data_dc_input_voltage_to_phys(uint16_t raw)
{
    return (float)raw * PCU_DATA_DC_INPUT_VOLTAGE_FACTOR + PCU_DATA_DC_INPUT_VOLTAGE_OFFSET;
}
static inline uint16_t pcu_data_dc_input_voltage_from_phys(float phys)
{
    float r = mapcan_round_f((phys - PCU_DATA_DC_INPUT_VOLTAGE_OFFSET) / PCU_DATA_DC_INPUT_VOLTAGE_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

#define PCU_DATA_DC_OUTPUT_CURRENT_FACTOR (10.0f)
#define PCU_DATA_DC_OUTPUT_CURRENT_OFFSET (0.0f)
/* dc_output_current: единица измерения — А */
static inline float pcu_data_dc_output_current_to_phys(uint16_t raw)
{
    return (float)raw * PCU_DATA_DC_OUTPUT_CURRENT_FACTOR + PCU_DATA_DC_OUTPUT_CURRENT_OFFSET;
}
static inline uint16_t pcu_data_dc_output_current_from_phys(float phys)
{
    float r = mapcan_round_f((phys - PCU_DATA_DC_OUTPUT_CURRENT_OFFSET) / PCU_DATA_DC_OUTPUT_CURRENT_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

#define PCU_DATA_DC_INPUT_CURRENT_FACTOR (10.0f)
#define PCU_DATA_DC_INPUT_CURRENT_OFFSET (0.0f)
/* dc_input_current: единица измерения — А */
static inline float pcu_data_dc_input_current_to_phys(uint16_t raw)
{
    return (float)raw * PCU_DATA_DC_INPUT_CURRENT_FACTOR + PCU_DATA_DC_INPUT_CURRENT_OFFSET;
}
static inline uint16_t pcu_data_dc_input_current_from_phys(float phys)
{
    float r = mapcan_round_f((phys - PCU_DATA_DC_INPUT_CURRENT_OFFSET) / PCU_DATA_DC_INPUT_CURRENT_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 65536.0f) { return 65535u; }
    return (uint16_t)r;
}

typedef struct {
    uint16_t dc_output_voltage; /* Выходное напряжение [В] */
    uint16_t dc_input_voltage; /* Входное напряжение [В] */
    uint16_t dc_output_current; /* Выходной ток [А] */
    uint16_t dc_input_current; /* Входной ток [А] */
} pcu_data_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void pcu_data_init(pcu_data_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int pcu_data_pack(uint8_t *data, size_t size, const pcu_data_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int pcu_data_unpack(pcu_data_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* pcu_command: Установка режима работы преобразователя */
#define PCU_COMMAND_ID 0x223u
#define PCU_COMMAND_LENGTH 2u
#define PCU_COMMAND_DLC PCU_COMMAND_LENGTH /* устарело: используйте PCU_COMMAND_LENGTH */
#define PCU_COMMAND_CYCLE_MS 50u

/* requested_mode: Запрашиваемый режим работы */
typedef enum {
    PCU_COMMAND_REQUESTED_MODE_STATE_INIT = 0, /* исходное состояние преобразователя */
    PCU_COMMAND_REQUESTED_MODE_STATE_PRECHARGE = 1, /* предзаряд входного конденсатора */
    PCU_COMMAND_REQUESTED_MODE_STATE_IDLE = 2, /* ключи закрыты, входной конденсатор предзаряжен, ошибок нет; ожидается команда заряда/разряда */
    PCU_COMMAND_REQUESTED_MODE_STATE_CHARGE = 3, /* заряд батареи */
    PCU_COMMAND_REQUESTED_MODE_STATE_DISCHARGE = 4, /* разряд батареи */
    PCU_COMMAND_REQUESTED_MODE_STATE_DIRECT_CHARGE = 5, /* батарея напрямую подключена к источнику для заряда */
    PCU_COMMAND_REQUESTED_MODE_STATE_DIRECT_DISCHARGE = 6, /* батарея напрямую подключена к нагрузке */
} pcu_command_requested_mode_t;

#define PCU_COMMAND_TARGET_VOLTAGE_FACTOR (10.0f)
#define PCU_COMMAND_TARGET_VOLTAGE_OFFSET (0.0f)
/* target_voltage: единица измерения — В */
static inline float pcu_command_target_voltage_to_phys(uint8_t raw)
{
    return (float)raw * PCU_COMMAND_TARGET_VOLTAGE_FACTOR + PCU_COMMAND_TARGET_VOLTAGE_OFFSET;
}
static inline uint8_t pcu_command_target_voltage_from_phys(float phys)
{
    float r = mapcan_round_f((phys - PCU_COMMAND_TARGET_VOLTAGE_OFFSET) / PCU_COMMAND_TARGET_VOLTAGE_FACTOR);
    if (r < 0.0f) { return 0u; }
    if (r >= 256.0f) { return 255u; }
    return (uint8_t)r;
}

typedef struct {
    uint8_t requested_mode; /* Запрашиваемый режим работы */
    uint8_t target_voltage; /* Целевое значение напряжения [В] */
} pcu_command_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void pcu_command_init(pcu_command_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int pcu_command_pack(uint8_t *data, size_t size, const pcu_command_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int pcu_command_unpack(pcu_command_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* bypass_command: Установка режима работы байпаса */
#define BYPASS_COMMAND_ID 0x224u
#define BYPASS_COMMAND_LENGTH 8u
#define BYPASS_COMMAND_DLC BYPASS_COMMAND_LENGTH /* устарело: используйте BYPASS_COMMAND_LENGTH */

typedef struct {
    uint8_t reserved_; /* сигналы не описаны */
} bypass_command_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void bypass_command_init(bypass_command_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int bypass_command_pack(uint8_t *data, size_t size, const bypass_command_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int bypass_command_unpack(bypass_command_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* bypass_state: Текущий режим работы ключа и состояние ошибки */
#define BYPASS_STATE_ID 0x2A4u
#define BYPASS_STATE_LENGTH 8u
#define BYPASS_STATE_DLC BYPASS_STATE_LENGTH /* устарело: используйте BYPASS_STATE_LENGTH */

typedef struct {
    uint8_t reserved_; /* сигналы не описаны */
} bypass_state_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void bypass_state_init(bypass_state_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int bypass_state_pack(uint8_t *data, size_t size, const bypass_state_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int bypass_state_unpack(bypass_state_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* cooling_command: Установка скорости вентиляторов и положения заслонок */
#define COOLING_COMMAND_ID 0x225u
#define COOLING_COMMAND_LENGTH 8u
#define COOLING_COMMAND_DLC COOLING_COMMAND_LENGTH /* устарело: используйте COOLING_COMMAND_LENGTH */

typedef struct {
    uint8_t reserved_; /* сигналы не описаны */
} cooling_command_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void cooling_command_init(cooling_command_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int cooling_command_pack(uint8_t *data, size_t size, const cooling_command_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int cooling_command_unpack(cooling_command_t *msg, const uint8_t *data, size_t size);

/* ------------------------------------------------------------------------ */
/* cooling_state: Скорость вентиляторов и положение заслонок */
#define COOLING_STATE_ID 0x2A5u
#define COOLING_STATE_LENGTH 8u
#define COOLING_STATE_DLC COOLING_STATE_LENGTH /* устарело: используйте COOLING_STATE_LENGTH */

typedef struct {
    uint8_t reserved_; /* сигналы не описаны */
} cooling_state_t;

/* Заполнить начальными значениями из карты (initial; без него — 0). */
void cooling_state_init(cooling_state_t *msg);
/* Упаковать: значение вне диапазона поля прижимается к границе; возвращает длину кадра или -1, если буфер короче кадра. */
int cooling_state_pack(uint8_t *data, size_t size, const cooling_state_t *msg);
/* Распаковать: возвращает 0 или -1, если данных меньше длины кадра. */
int cooling_state_unpack(cooling_state_t *msg, const uint8_t *data, size_t size);

#ifdef __cplusplus
}
#endif

#endif /* BUS1_MAPCAN_H */
