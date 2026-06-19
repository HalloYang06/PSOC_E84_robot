#include "rehab_trajectory_bank.h"

#include "control_layer_cfg.h"

typedef struct
{
    struct rt_mutex lock;
    rehab_trajectory_sample_t samples[CONTROL_REHAB_TRAJECTORY_MAX_SAMPLES];
    rt_uint16_t count;
    rt_bool_t initialized;
} rehab_trajectory_bank_t;

static rehab_trajectory_bank_t s_rehab_trajectory;

static rt_err_t rehab_trajectory_check_slot(rt_uint8_t slot)
{
    if (slot != 0U)
    {
        return -RT_ENOSYS;
    }
    return RT_EOK;
}

void rehab_trajectory_bank_init(void)
{
    if (s_rehab_trajectory.initialized)
    {
        return;
    }

    rt_memset(&s_rehab_trajectory, 0, sizeof(s_rehab_trajectory));
    if (rt_mutex_init(&s_rehab_trajectory.lock, "rehabtb", RT_IPC_FLAG_PRIO) == RT_EOK)
    {
        s_rehab_trajectory.initialized = RT_TRUE;
    }
}

rt_err_t rehab_trajectory_bank_clear(rt_uint8_t slot)
{
    rt_err_t ret = rehab_trajectory_check_slot(slot);

    if (ret != RT_EOK)
    {
        return ret;
    }
    rehab_trajectory_bank_init();

    rt_mutex_take(&s_rehab_trajectory.lock, RT_WAITING_FOREVER);
    s_rehab_trajectory.count = 0U;
    rt_mutex_release(&s_rehab_trajectory.lock);
    return RT_EOK;
}

rt_err_t rehab_trajectory_bank_append(rt_uint8_t slot,
                                      const rehab_trajectory_sample_t *sample)
{
    rt_err_t ret = rehab_trajectory_check_slot(slot);

    if (ret != RT_EOK)
    {
        return ret;
    }
    if (sample == RT_NULL)
    {
        return -RT_EINVAL;
    }
    rehab_trajectory_bank_init();

    rt_mutex_take(&s_rehab_trajectory.lock, RT_WAITING_FOREVER);
    if (s_rehab_trajectory.count >= CONTROL_REHAB_TRAJECTORY_MAX_SAMPLES)
    {
        rt_mutex_release(&s_rehab_trajectory.lock);
        return -RT_EFULL;
    }
    s_rehab_trajectory.samples[s_rehab_trajectory.count++] = *sample;
    rt_mutex_release(&s_rehab_trajectory.lock);
    return RT_EOK;
}

rt_err_t rehab_trajectory_bank_get(rt_uint8_t slot,
                                   rt_uint16_t index,
                                   rehab_trajectory_sample_t *out)
{
    rt_err_t ret = rehab_trajectory_check_slot(slot);

    if (ret != RT_EOK)
    {
        return ret;
    }
    if (out == RT_NULL)
    {
        return -RT_EINVAL;
    }
    rehab_trajectory_bank_init();

    rt_mutex_take(&s_rehab_trajectory.lock, RT_WAITING_FOREVER);
    if (index >= s_rehab_trajectory.count)
    {
        rt_mutex_release(&s_rehab_trajectory.lock);
        return -RT_EEMPTY;
    }
    *out = s_rehab_trajectory.samples[index];
    rt_mutex_release(&s_rehab_trajectory.lock);
    return RT_EOK;
}

rt_uint16_t rehab_trajectory_bank_count(rt_uint8_t slot)
{
    rt_uint16_t count = 0U;

    if (rehab_trajectory_check_slot(slot) != RT_EOK)
    {
        return 0U;
    }
    rehab_trajectory_bank_init();

    rt_mutex_take(&s_rehab_trajectory.lock, RT_WAITING_FOREVER);
    count = s_rehab_trajectory.count;
    rt_mutex_release(&s_rehab_trajectory.lock);
    return count;
}

rt_bool_t rehab_trajectory_bank_has_data(rt_uint8_t slot)
{
    return (rehab_trajectory_bank_count(slot) > 0U) ? RT_TRUE : RT_FALSE;
}
