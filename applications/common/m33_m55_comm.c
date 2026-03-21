#include "m33_m55_comm.h"

static struct
{
    struct rt_mutex lock;
    m33_m55_message_t last_msg;
    rt_bool_t has_msg;
    rt_uint32_t seq;
} g_comm;

rt_err_t m33_m55_comm_init(void)
{
    rt_mutex_init(&g_comm.lock, "m33m55", RT_IPC_FLAG_PRIO);
    g_comm.has_msg = RT_FALSE;
    g_comm.seq = 0;
    return RT_EOK;
}

rt_err_t m33_m55_comm_publish(const m33_m55_message_t *msg)
{
    if (msg == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_comm.lock, RT_WAITING_FOREVER);
    g_comm.last_msg = *msg;
    g_comm.last_msg.seq = ++g_comm.seq;
    g_comm.has_msg = RT_TRUE;
    rt_mutex_release(&g_comm.lock);
    return RT_EOK;
}

rt_err_t m33_m55_comm_consume(m33_m55_message_t *msg)
{
    if (msg == RT_NULL)
    {
        return -RT_ERROR;
    }

    rt_mutex_take(&g_comm.lock, RT_WAITING_FOREVER);
    if (!g_comm.has_msg)
    {
        rt_mutex_release(&g_comm.lock);
        return -RT_EEMPTY;
    }

    *msg = g_comm.last_msg;
    g_comm.has_msg = RT_FALSE;
    rt_mutex_release(&g_comm.lock);
    return RT_EOK;
}
