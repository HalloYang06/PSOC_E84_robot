#ifndef APP_TYPES_H
#define APP_TYPES_H

#include <stdbool.h>
#include <stdint.h>

typedef enum
{
    NODE_STATE_INIT = 0,
    NODE_STATE_RUN = 1,
    NODE_STATE_DEGRADED = 2,
    NODE_STATE_FAULT = 3
} node_state_t;

typedef enum
{
    APP_OK = 0,
    APP_ERR_INVALID_ARG = -1,
    APP_ERR_BUSY = -2,
    APP_ERR_IO = -3,
    APP_ERR_TIMEOUT = -4,
    APP_ERR_OVERFLOW = -5,
    APP_ERR_NOT_READY = -6
} app_status_t;

#endif
