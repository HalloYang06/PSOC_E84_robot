#ifndef TEST_HOST_RTTHREAD_H
#define TEST_HOST_RTTHREAD_H

#include <stdint.h>
#include <string.h>

typedef int rt_bool_t;
typedef int rt_err_t;
typedef uint8_t rt_uint8_t;
typedef uint16_t rt_uint16_t;
typedef int16_t rt_int16_t;
typedef uint32_t rt_uint32_t;
typedef int32_t rt_int32_t;
typedef uint64_t rt_uint64_t;
typedef unsigned int rt_tick_t;

#ifndef RT_TRUE
#define RT_TRUE 1
#endif

#ifndef RT_FALSE
#define RT_FALSE 0
#endif

#ifndef RT_NULL
#define RT_NULL ((void *)0)
#endif

#ifndef RT_EOK
#define RT_EOK 0
#endif

#define rt_memset memset

#endif /* TEST_HOST_RTTHREAD_H */
