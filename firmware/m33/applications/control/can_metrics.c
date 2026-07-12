#include "can_metrics.h"

#include <finsh.h>
#include <stdlib.h>
#include <string.h>

#include "drv_can.h"

#define CANM_ID_SLOTS           24U
#define CANM_SAMPLE_DEPTH       32U
#define CANM_LATENCY_PAIRS      4U
#define CANM_DEFAULT_BITRATE    1000000U

typedef struct
{
    rt_bool_t used;
    rt_uint32_t id;
    rt_uint8_t ide;
    rt_uint32_t rx_frames;
    rt_uint32_t tx_frames;
    rt_uint32_t rx_bytes;
    rt_uint32_t tx_bytes;
    rt_uint32_t expected_period_ms;
    rt_bool_t have_last_rx_ms;
    rt_uint32_t last_rx_ms;
    rt_uint32_t last_period_ms;
    rt_uint32_t period_samples[CANM_SAMPLE_DEPTH];
    rt_uint32_t jitter_samples[CANM_SAMPLE_DEPTH];
    rt_uint8_t period_count;
    rt_uint8_t period_pos;
    rt_uint8_t jitter_count;
    rt_uint8_t jitter_pos;
    rt_bool_t seq_enabled;
    rt_uint8_t seq_offset;
    rt_bool_t have_last_seq;
    rt_uint8_t last_seq;
    rt_uint32_t seq_lost;
    rt_uint32_t seq_dup;
} canm_id_stat_t;

typedef struct
{
    rt_bool_t used;
    rt_uint32_t tx_id;
    rt_uint8_t tx_ide;
    rt_uint8_t tx_seq_offset;
    rt_uint32_t rx_id;
    rt_uint8_t rx_ide;
    rt_uint8_t rx_seq_offset;
    rt_bool_t tx_seq_valid[256];
    rt_uint32_t tx_seq_ms[256];
    rt_uint32_t latency_samples[CANM_SAMPLE_DEPTH];
    rt_uint8_t latency_count;
    rt_uint8_t latency_pos;
    rt_uint32_t matched;
    rt_uint32_t unmatched_rx;
    rt_uint32_t overwritten_tx;
} canm_latency_pair_t;

static canm_id_stat_t s_id_stats[CANM_ID_SLOTS];
static canm_latency_pair_t s_latency_pairs[CANM_LATENCY_PAIRS];
static rt_uint32_t s_bitrate = CANM_DEFAULT_BITRATE;
static rt_uint32_t s_reset_ms;
static rt_uint32_t s_rx_frames;
static rt_uint32_t s_tx_frames;
static rt_uint32_t s_rx_bytes;
static rt_uint32_t s_tx_bytes;
static rt_uint64_t s_est_bits;
static rt_uint32_t s_id_overflow;
static rt_uint32_t s_tx_fail;
static rt_uint32_t s_rx_drain_limit_hits;
static rt_uint8_t s_have_hw_base;
static rt_uint8_t s_hw_base_cel;

static rt_uint32_t canm_now_ms(void)
{
    return (rt_uint32_t)rt_tick_get_millisecond();
}

static rt_uint8_t canm_parse_ide(int argc, char **argv, int index)
{
    if (index >= argc)
    {
        return RT_CAN_STDID;
    }

    if ((argv[index][0] == 'e') || (argv[index][0] == 'E'))
    {
        return RT_CAN_EXTID;
    }

    if ((argv[index][0] == 's') || (argv[index][0] == 'S'))
    {
        return RT_CAN_STDID;
    }

    return (strtoul(argv[index], RT_NULL, 0) != 0UL) ? RT_CAN_EXTID : RT_CAN_STDID;
}

static rt_uint32_t canm_frame_bits(const struct rt_can_msg *msg)
{
    rt_uint32_t base_bits;
    rt_uint32_t raw_bits;
    rt_uint32_t len;

    if (msg == RT_NULL)
    {
        return 0U;
    }

    len = (msg->len > 8U) ? 8U : msg->len;
    base_bits = (msg->ide == RT_CAN_EXTID) ? 67U : 47U;
    raw_bits = base_bits + (len * 8U);

    return raw_bits + ((raw_bits + 4U) / 5U);
}

static void canm_sample_push(rt_uint32_t *samples,
                             rt_uint8_t *count,
                             rt_uint8_t *pos,
                             rt_uint32_t value)
{
    samples[*pos] = value;
    *pos = (rt_uint8_t)((*pos + 1U) % CANM_SAMPLE_DEPTH);
    if (*count < CANM_SAMPLE_DEPTH)
    {
        (*count)++;
    }
}

static rt_uint32_t canm_quantile(const rt_uint32_t *samples, rt_uint8_t count, rt_uint8_t pct)
{
    rt_uint32_t copy[CANM_SAMPLE_DEPTH];
    rt_uint8_t i;
    rt_uint8_t j;
    rt_uint8_t idx;

    if (count == 0U)
    {
        return 0U;
    }

    for (i = 0U; i < count; i++)
    {
        copy[i] = samples[i];
    }

    for (i = 1U; i < count; i++)
    {
        rt_uint32_t value = copy[i];
        j = i;
        while ((j > 0U) && (copy[j - 1U] > value))
        {
            copy[j] = copy[j - 1U];
            j--;
        }
        copy[j] = value;
    }

    idx = (rt_uint8_t)(((rt_uint32_t)count * (rt_uint32_t)pct + 99U) / 100U);
    if (idx == 0U)
    {
        idx = 1U;
    }
    idx--;
    if (idx >= count)
    {
        idx = count - 1U;
    }

    return copy[idx];
}

static canm_id_stat_t *canm_find_slot(rt_uint32_t id, rt_uint8_t ide, rt_bool_t create)
{
    rt_uint8_t i;
    rt_uint8_t free_i = 0xFFU;

    for (i = 0U; i < CANM_ID_SLOTS; i++)
    {
        if (s_id_stats[i].used)
        {
            if ((s_id_stats[i].id == id) && (s_id_stats[i].ide == ide))
            {
                return &s_id_stats[i];
            }
        }
        else if (free_i == 0xFFU)
        {
            free_i = i;
        }
    }

    if (!create || (free_i == 0xFFU))
    {
        if (create)
        {
            s_id_overflow++;
        }
        return RT_NULL;
    }

    rt_memset(&s_id_stats[free_i], 0, sizeof(s_id_stats[free_i]));
    s_id_stats[free_i].used = RT_TRUE;
    s_id_stats[free_i].id = id;
    s_id_stats[free_i].ide = ide;
    return &s_id_stats[free_i];
}

static void canm_track_period(canm_id_stat_t *slot, rt_uint32_t now_ms)
{
    rt_uint32_t period_ms;
    rt_uint32_t jitter_ms = 0U;
    rt_bool_t push_jitter = RT_FALSE;

    if (slot == RT_NULL)
    {
        return;
    }

    if (!slot->have_last_rx_ms)
    {
        slot->last_rx_ms = now_ms;
        slot->have_last_rx_ms = RT_TRUE;
        return;
    }

    period_ms = now_ms - slot->last_rx_ms;
    slot->last_rx_ms = now_ms;
    canm_sample_push(slot->period_samples,
                     &slot->period_count,
                     &slot->period_pos,
                     period_ms);

    if (slot->expected_period_ms > 0U)
    {
        jitter_ms = (period_ms > slot->expected_period_ms) ?
                    (period_ms - slot->expected_period_ms) :
                    (slot->expected_period_ms - period_ms);
        push_jitter = RT_TRUE;
    }
    else if (slot->last_period_ms > 0U)
    {
        jitter_ms = (period_ms > slot->last_period_ms) ?
                    (period_ms - slot->last_period_ms) :
                    (slot->last_period_ms - period_ms);
        push_jitter = RT_TRUE;
    }

    slot->last_period_ms = period_ms;
    if (push_jitter)
    {
        canm_sample_push(slot->jitter_samples,
                         &slot->jitter_count,
                         &slot->jitter_pos,
                         jitter_ms);
    }
}

static void canm_track_seq(canm_id_stat_t *slot, const struct rt_can_msg *msg)
{
    rt_uint8_t seq;
    rt_uint8_t expected;
    rt_uint8_t gap;

    if ((slot == RT_NULL) || !slot->seq_enabled || (msg == RT_NULL))
    {
        return;
    }

    if (msg->len <= slot->seq_offset)
    {
        return;
    }

    seq = msg->data[slot->seq_offset];
    if (!slot->have_last_seq)
    {
        slot->last_seq = seq;
        slot->have_last_seq = RT_TRUE;
        return;
    }

    expected = (rt_uint8_t)(slot->last_seq + 1U);
    if (seq == slot->last_seq)
    {
        slot->seq_dup++;
    }
    else if (seq != expected)
    {
        gap = (rt_uint8_t)(seq - expected);
        slot->seq_lost += (rt_uint32_t)gap;
    }

    slot->last_seq = seq;
}

static void canm_track_latency_tx(const struct rt_can_msg *msg, rt_uint32_t now_ms)
{
    rt_uint8_t i;

    if (msg == RT_NULL)
    {
        return;
    }

    for (i = 0U; i < CANM_LATENCY_PAIRS; i++)
    {
        canm_latency_pair_t *pair = &s_latency_pairs[i];
        rt_uint8_t seq;

        if (!pair->used ||
            (pair->tx_id != msg->id) ||
            (pair->tx_ide != msg->ide) ||
            (msg->len <= pair->tx_seq_offset))
        {
            continue;
        }

        seq = msg->data[pair->tx_seq_offset];
        if (pair->tx_seq_valid[seq])
        {
            pair->overwritten_tx++;
        }
        pair->tx_seq_valid[seq] = RT_TRUE;
        pair->tx_seq_ms[seq] = now_ms;
    }
}

static void canm_track_latency_rx(const struct rt_can_msg *msg, rt_uint32_t now_ms)
{
    rt_uint8_t i;

    if (msg == RT_NULL)
    {
        return;
    }

    for (i = 0U; i < CANM_LATENCY_PAIRS; i++)
    {
        canm_latency_pair_t *pair = &s_latency_pairs[i];
        rt_uint8_t seq;
        rt_uint32_t latency_ms;

        if (!pair->used ||
            (pair->rx_id != msg->id) ||
            (pair->rx_ide != msg->ide) ||
            (msg->len <= pair->rx_seq_offset))
        {
            continue;
        }

        seq = msg->data[pair->rx_seq_offset];
        if (!pair->tx_seq_valid[seq])
        {
            pair->unmatched_rx++;
            continue;
        }

        latency_ms = now_ms - pair->tx_seq_ms[seq];
        pair->tx_seq_valid[seq] = RT_FALSE;
        pair->matched++;
        canm_sample_push(pair->latency_samples,
                         &pair->latency_count,
                         &pair->latency_pos,
                         latency_ms);
    }
}

void can_metrics_reset(void)
{
    ifx_can_direct_diag_t diag;

    rt_memset(s_id_stats, 0, sizeof(s_id_stats));
    rt_memset(s_latency_pairs, 0, sizeof(s_latency_pairs));
    s_reset_ms = canm_now_ms();
    s_rx_frames = 0U;
    s_tx_frames = 0U;
    s_rx_bytes = 0U;
    s_tx_bytes = 0U;
    s_est_bits = 0U;
    s_id_overflow = 0U;
    s_tx_fail = 0U;
    s_rx_drain_limit_hits = 0U;
    s_have_hw_base = 0U;
    s_hw_base_cel = 0U;

    if (ifx_can_direct_get_diag(&diag) == RT_EOK)
    {
        s_have_hw_base = 1U;
        s_hw_base_cel = (rt_uint8_t)_FLD2VAL(CANFD_CH_M_TTCAN_ECR_CEL, diag.ecr);
        if (diag.bitrate > 0U)
        {
            s_bitrate = diag.bitrate;
        }
    }
}

void can_metrics_set_bitrate(rt_uint32_t bitrate)
{
    if (bitrate > 0U)
    {
        s_bitrate = bitrate;
    }
}

void can_metrics_record_tx(const struct rt_can_msg *msg, rt_err_t result)
{
    canm_id_stat_t *slot;
    rt_uint32_t len;
    rt_uint32_t now_ms;

    if (msg == RT_NULL)
    {
        return;
    }

    if (result != RT_EOK)
    {
        s_tx_fail++;
        return;
    }

    now_ms = canm_now_ms();
    len = (msg->len > 8U) ? 8U : msg->len;
    s_tx_frames++;
    s_tx_bytes += len;
    s_est_bits += canm_frame_bits(msg);

    slot = canm_find_slot(msg->id, msg->ide, RT_TRUE);
    if (slot != RT_NULL)
    {
        slot->tx_frames++;
        slot->tx_bytes += len;
    }

    canm_track_latency_tx(msg, now_ms);
}

void can_metrics_record_rx(const struct rt_can_msg *msg)
{
    canm_id_stat_t *slot;
    rt_uint32_t len;
    rt_uint32_t now_ms;

    if (msg == RT_NULL)
    {
        return;
    }

    now_ms = canm_now_ms();
    len = (msg->len > 8U) ? 8U : msg->len;
    s_rx_frames++;
    s_rx_bytes += len;
    s_est_bits += canm_frame_bits(msg);

    slot = canm_find_slot(msg->id, msg->ide, RT_TRUE);
    if (slot != RT_NULL)
    {
        slot->rx_frames++;
        slot->rx_bytes += len;
        canm_track_period(slot, now_ms);
        canm_track_seq(slot, msg);
    }

    canm_track_latency_rx(msg, now_ms);
}

void can_metrics_record_rx_drain_limit(void)
{
    s_rx_drain_limit_hits++;
}

static void canm_print_rate_x100(const char *name, rt_uint32_t value_x100)
{
    rt_kprintf("%s=%lu.%02lu",
               name,
               (unsigned long)(value_x100 / 100U),
               (unsigned long)(value_x100 % 100U));
}

static void canm_print_summary(void)
{
    ifx_can_direct_diag_t diag;
    rt_uint32_t now_ms = canm_now_ms();
    rt_uint32_t elapsed_ms = now_ms - s_reset_ms;
    rt_uint32_t frames = s_rx_frames + s_tx_frames;
    rt_uint32_t payload_bytes = s_rx_bytes + s_tx_bytes;
    rt_uint32_t fps_x100 = 0U;
    rt_uint32_t payload_bps = 0U;
    rt_uint32_t util_permille = 0U;
    rt_uint8_t cel = 0U;
    rt_uint8_t cel_delta = 0U;
    rt_uint8_t tec = 0U;
    rt_uint8_t rec = 0U;
    rt_uint8_t lec = 0U;
    rt_uint8_t dlec = 0U;
    rt_err_t diag_ret;

    if (elapsed_ms == 0U)
    {
        elapsed_ms = 1U;
    }

    fps_x100 = (rt_uint32_t)(((rt_uint64_t)frames * 100000ULL) / elapsed_ms);
    payload_bps = (rt_uint32_t)(((rt_uint64_t)payload_bytes * 1000ULL) / elapsed_ms);
    if (s_bitrate > 0U)
    {
        util_permille = (rt_uint32_t)((s_est_bits * 1000000ULL) /
                                     ((rt_uint64_t)s_bitrate * elapsed_ms));
    }

    rt_kprintf("CANM_SUM: elapsed_ms=%lu bitrate=%lu rx=%lu tx=%lu ",
               (unsigned long)elapsed_ms,
               (unsigned long)s_bitrate,
               (unsigned long)s_rx_frames,
               (unsigned long)s_tx_frames);
    canm_print_rate_x100("frames_s", fps_x100);
    rt_kprintf(" payload_Bps=%lu util_permille=%lu est_bits=%lu tx_fail=%lu id_overflow=%lu\n",
               (unsigned long)payload_bps,
               (unsigned long)util_permille,
               (unsigned long)((s_est_bits > 0xFFFFFFFFULL) ? 0xFFFFFFFFUL : (rt_uint32_t)s_est_bits),
               (unsigned long)s_tx_fail,
               (unsigned long)s_id_overflow);

    diag_ret = ifx_can_direct_get_diag(&diag);
    if (diag_ret == RT_EOK)
    {
        tec = (rt_uint8_t)_FLD2VAL(CANFD_CH_M_TTCAN_ECR_TEC, diag.ecr);
        rec = (rt_uint8_t)_FLD2VAL(CANFD_CH_M_TTCAN_ECR_REC, diag.ecr);
        cel = (rt_uint8_t)_FLD2VAL(CANFD_CH_M_TTCAN_ECR_CEL, diag.ecr);
        lec = (rt_uint8_t)_FLD2VAL(CANFD_CH_M_TTCAN_PSR_LEC, diag.psr);
        dlec = (rt_uint8_t)_FLD2VAL(CANFD_CH_M_TTCAN_PSR_DLEC, diag.psr);
        if (s_have_hw_base)
        {
            cel_delta = (rt_uint8_t)(cel - s_hw_base_cel);
        }

        rt_kprintf("CANM_ERR: ready=%u tec=%u rec=%u cel=%u cel_delta=%u lec=%u dlec=%u ep=%u ew=%u bo=%u psr=0x%08lx ecr=0x%08lx ir=0x%08lx\n",
                   diag.ready ? 1U : 0U,
                   (unsigned int)tec,
                   (unsigned int)rec,
                   (unsigned int)cel,
                   (unsigned int)cel_delta,
                   (unsigned int)lec,
                   (unsigned int)dlec,
                   ((diag.psr & CANFD_CH_M_TTCAN_PSR_EP_Msk) != 0U) ? 1U : 0U,
                   ((diag.psr & CANFD_CH_M_TTCAN_PSR_EW_Msk) != 0U) ? 1U : 0U,
                   ((diag.psr & CANFD_CH_M_TTCAN_PSR_BO_Msk) != 0U) ? 1U : 0U,
                   (unsigned long)diag.psr,
                   (unsigned long)diag.ecr,
                   (unsigned long)diag.ir);
        rt_kprintf("CANM_Q: rxf0_fill=%lu rxf0_full=%lu rxf0_lost=%lu rx_lost_count=%lu rx_full_count=%lu rx_extract_fail=%lu rx_drain_limit=%lu tx_timeout=%lu tx_send_fail=%lu tx_pending_suppressed=%lu txbrp=0x%08lx txbto=0x%08lx txbcf=0x%08lx\n",
                   (unsigned long)_FLD2VAL(CANFD_CH_M_TTCAN_RXF0S_F0FL, diag.rxf0s),
                   (unsigned long)_FLD2VAL(CANFD_CH_M_TTCAN_RXF0S_F0F, diag.rxf0s),
                   (unsigned long)_FLD2VAL(CANFD_CH_M_TTCAN_RXF0S_RF0L, diag.rxf0s),
                   (unsigned long)diag.rx_fifo0_lost_count,
                   (unsigned long)diag.rx_fifo0_full_count,
                   (unsigned long)diag.rx_extract_fail_count,
                   (unsigned long)s_rx_drain_limit_hits,
                   (unsigned long)diag.tx_timeout_count,
                   (unsigned long)diag.tx_send_fail_count,
                   (unsigned long)diag.tx_pending_suppressed_count,
                   (unsigned long)diag.txbrp,
                   (unsigned long)diag.txbto,
                   (unsigned long)diag.txbcf);
    }
    else
    {
        rt_kprintf("CANM_ERR: direct_diag_unavailable ret=%d\n", diag_ret);
    }
}

static void canm_print_ids(void)
{
    rt_uint8_t i;
    rt_uint32_t now_ms = canm_now_ms();
    rt_uint32_t elapsed_ms = now_ms - s_reset_ms;

    if (elapsed_ms == 0U)
    {
        elapsed_ms = 1U;
    }

    for (i = 0U; i < CANM_ID_SLOTS; i++)
    {
        canm_id_stat_t *slot = &s_id_stats[i];
        rt_uint32_t rx_fps_x100;
        rt_uint32_t tx_fps_x100;

        if (!slot->used)
        {
            continue;
        }

        rx_fps_x100 = (rt_uint32_t)(((rt_uint64_t)slot->rx_frames * 100000ULL) / elapsed_ms);
        tx_fps_x100 = (rt_uint32_t)(((rt_uint64_t)slot->tx_frames * 100000ULL) / elapsed_ms);

        rt_kprintf("CANM_ID: id=0x%08lx ide=%u rx=%lu tx=%lu ",
                   (unsigned long)slot->id,
                   (unsigned int)slot->ide,
                   (unsigned long)slot->rx_frames,
                   (unsigned long)slot->tx_frames);
        canm_print_rate_x100("rx_fps", rx_fps_x100);
        rt_kprintf(" ");
        canm_print_rate_x100("tx_fps", tx_fps_x100);
        rt_kprintf(" period_p50=%lums period_p95=%lums period_p99=%lums period_max=%lums expected=%lums jitter_p95=%lums jitter_max=%lums seq_off=%d seq_lost=%lu seq_dup=%lu\n",
                   (unsigned long)canm_quantile(slot->period_samples, slot->period_count, 50U),
                   (unsigned long)canm_quantile(slot->period_samples, slot->period_count, 95U),
                   (unsigned long)canm_quantile(slot->period_samples, slot->period_count, 99U),
                   (unsigned long)canm_quantile(slot->period_samples, slot->period_count, 100U),
                   (unsigned long)slot->expected_period_ms,
                   (unsigned long)canm_quantile(slot->jitter_samples, slot->jitter_count, 95U),
                   (unsigned long)canm_quantile(slot->jitter_samples, slot->jitter_count, 100U),
                   slot->seq_enabled ? (int)slot->seq_offset : -1,
                   (unsigned long)slot->seq_lost,
                   (unsigned long)slot->seq_dup);
    }
}

static void canm_print_latency(void)
{
    rt_uint8_t i;

    for (i = 0U; i < CANM_LATENCY_PAIRS; i++)
    {
        canm_latency_pair_t *pair = &s_latency_pairs[i];

        if (!pair->used)
        {
            continue;
        }

        rt_kprintf("CANM_LAT: idx=%u tx=0x%08lx/%u tx_seq_off=%u rx=0x%08lx/%u rx_seq_off=%u matched=%lu unmatched_rx=%lu overwritten_tx=%lu p50=%lums p95=%lums p99=%lums max=%lums\n",
                   (unsigned int)i,
                   (unsigned long)pair->tx_id,
                   (unsigned int)pair->tx_ide,
                   (unsigned int)pair->tx_seq_offset,
                   (unsigned long)pair->rx_id,
                   (unsigned int)pair->rx_ide,
                   (unsigned int)pair->rx_seq_offset,
                   (unsigned long)pair->matched,
                   (unsigned long)pair->unmatched_rx,
                   (unsigned long)pair->overwritten_tx,
                   (unsigned long)canm_quantile(pair->latency_samples, pair->latency_count, 50U),
                   (unsigned long)canm_quantile(pair->latency_samples, pair->latency_count, 95U),
                   (unsigned long)canm_quantile(pair->latency_samples, pair->latency_count, 99U),
                   (unsigned long)canm_quantile(pair->latency_samples, pair->latency_count, 100U));
    }
}

static rt_err_t canm_expect_config(rt_uint32_t id, rt_uint8_t ide, rt_uint32_t period_ms)
{
    canm_id_stat_t *slot = canm_find_slot(id, ide, RT_TRUE);

    if (slot == RT_NULL)
    {
        return -RT_ENOMEM;
    }

    slot->expected_period_ms = period_ms;
    return RT_EOK;
}

static rt_err_t canm_seq_config(rt_uint32_t id, rt_uint8_t ide, rt_uint8_t seq_offset)
{
    canm_id_stat_t *slot = canm_find_slot(id, ide, RT_TRUE);

    if (slot == RT_NULL)
    {
        return -RT_ENOMEM;
    }

    slot->seq_enabled = RT_TRUE;
    slot->seq_offset = seq_offset;
    slot->have_last_seq = RT_FALSE;
    slot->seq_lost = 0U;
    slot->seq_dup = 0U;
    return RT_EOK;
}

static rt_err_t canm_pair_config(rt_uint32_t tx_id,
                                 rt_uint8_t tx_ide,
                                 rt_uint8_t tx_seq_offset,
                                 rt_uint32_t rx_id,
                                 rt_uint8_t rx_ide,
                                 rt_uint8_t rx_seq_offset)
{
    rt_uint8_t i;
    rt_uint8_t free_i = 0xFFU;

    for (i = 0U; i < CANM_LATENCY_PAIRS; i++)
    {
        if (s_latency_pairs[i].used)
        {
            if ((s_latency_pairs[i].tx_id == tx_id) &&
                (s_latency_pairs[i].tx_ide == tx_ide) &&
                (s_latency_pairs[i].rx_id == rx_id) &&
                (s_latency_pairs[i].rx_ide == rx_ide))
            {
                break;
            }
        }
        else if (free_i == 0xFFU)
        {
            free_i = i;
        }
    }

    if (i >= CANM_LATENCY_PAIRS)
    {
        if (free_i == 0xFFU)
        {
            return -RT_ENOMEM;
        }
        i = free_i;
    }

    rt_memset(&s_latency_pairs[i], 0, sizeof(s_latency_pairs[i]));
    s_latency_pairs[i].used = RT_TRUE;
    s_latency_pairs[i].tx_id = tx_id;
    s_latency_pairs[i].tx_ide = tx_ide;
    s_latency_pairs[i].tx_seq_offset = tx_seq_offset;
    s_latency_pairs[i].rx_id = rx_id;
    s_latency_pairs[i].rx_ide = rx_ide;
    s_latency_pairs[i].rx_seq_offset = rx_seq_offset;
    return RT_EOK;
}

static int cmd_canm_reset(int argc, char **argv)
{
    if (argc >= 2)
    {
        can_metrics_set_bitrate((rt_uint32_t)strtoul(argv[1], RT_NULL, 0));
    }

    can_metrics_reset();
    rt_kprintf("canm_reset bitrate=%lu\n", (unsigned long)s_bitrate);
    return 0;
}
MSH_CMD_EXPORT(cmd_canm_reset, reset CAN metrics: canm_reset [bitrate]);
MSH_CMD_EXPORT_ALIAS(cmd_canm_reset, canm_reset, reset CAN metrics: canm_reset [bitrate]);

static int cmd_canm_show(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    canm_print_summary();
    canm_print_latency();
    return 0;
}
MSH_CMD_EXPORT(cmd_canm_show, show CAN bus metric summary);
MSH_CMD_EXPORT_ALIAS(cmd_canm_show, canm_show, show CAN bus metric summary);

static int cmd_canm_ids(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    canm_print_ids();
    return 0;
}
MSH_CMD_EXPORT(cmd_canm_ids, show per CAN ID period and seq metrics);
MSH_CMD_EXPORT_ALIAS(cmd_canm_ids, canm_ids, show per CAN ID period and seq metrics);

static int cmd_canm_expect(int argc, char **argv)
{
    rt_uint32_t id;
    rt_uint32_t period_ms;
    rt_uint8_t ide;
    rt_err_t ret;

    if (argc < 3)
    {
        rt_kprintf("usage: canm_expect <id> <period_ms> [std|ext|0|1]\n");
        return -1;
    }

    id = (rt_uint32_t)strtoul(argv[1], RT_NULL, 0);
    period_ms = (rt_uint32_t)strtoul(argv[2], RT_NULL, 0);
    ide = canm_parse_ide(argc, argv, 3);
    ret = canm_expect_config(id, ide, period_ms);
    rt_kprintf("canm_expect id=0x%08lx ide=%u period_ms=%lu ret=%d\n",
               (unsigned long)id,
               (unsigned int)ide,
               (unsigned long)period_ms,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_canm_expect, configure expected RX period for one CAN ID);
MSH_CMD_EXPORT_ALIAS(cmd_canm_expect, canm_expect, configure expected RX period for one CAN ID);

static int cmd_canm_seq(int argc, char **argv)
{
    rt_uint32_t id;
    rt_uint8_t offset;
    rt_uint8_t ide;
    rt_err_t ret;

    if (argc < 3)
    {
        rt_kprintf("usage: canm_seq <id> <seq_offset> [std|ext|0|1]\n");
        return -1;
    }

    id = (rt_uint32_t)strtoul(argv[1], RT_NULL, 0);
    offset = (rt_uint8_t)strtoul(argv[2], RT_NULL, 0);
    ide = canm_parse_ide(argc, argv, 3);
    if (offset >= 8U)
    {
        rt_kprintf("canm_seq invalid offset=%u\n", (unsigned int)offset);
        return -RT_EINVAL;
    }

    ret = canm_seq_config(id, ide, offset);
    rt_kprintf("canm_seq id=0x%08lx ide=%u offset=%u ret=%d\n",
               (unsigned long)id,
               (unsigned int)ide,
               (unsigned int)offset,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_canm_seq, configure seq loss tracking for one RX CAN ID);
MSH_CMD_EXPORT_ALIAS(cmd_canm_seq, canm_seq, configure seq loss tracking for one RX CAN ID);

static int cmd_canm_pair(int argc, char **argv)
{
    rt_uint32_t tx_id;
    rt_uint32_t rx_id;
    rt_uint8_t tx_off;
    rt_uint8_t rx_off;
    rt_uint8_t tx_ide;
    rt_uint8_t rx_ide;
    rt_err_t ret;

    if (argc < 5)
    {
        rt_kprintf("usage: canm_pair <tx_id> <tx_seq_off> <rx_id> <rx_seq_off> [std|ext|0|1]\n");
        rt_kprintf("example: canm_pair 0x7C0 1 0x7C1 1 std\n");
        return -1;
    }

    tx_id = (rt_uint32_t)strtoul(argv[1], RT_NULL, 0);
    tx_off = (rt_uint8_t)strtoul(argv[2], RT_NULL, 0);
    rx_id = (rt_uint32_t)strtoul(argv[3], RT_NULL, 0);
    rx_off = (rt_uint8_t)strtoul(argv[4], RT_NULL, 0);
    tx_ide = canm_parse_ide(argc, argv, 5);
    rx_ide = tx_ide;
    if ((tx_off >= 8U) || (rx_off >= 8U))
    {
        rt_kprintf("canm_pair invalid offsets tx=%u rx=%u\n",
                   (unsigned int)tx_off,
                   (unsigned int)rx_off);
        return -RT_EINVAL;
    }

    ret = canm_pair_config(tx_id, tx_ide, tx_off, rx_id, rx_ide, rx_off);
    rt_kprintf("canm_pair tx=0x%08lx/%u off=%u rx=0x%08lx/%u off=%u ret=%d\n",
               (unsigned long)tx_id,
               (unsigned int)tx_ide,
               (unsigned int)tx_off,
               (unsigned long)rx_id,
               (unsigned int)rx_ide,
               (unsigned int)rx_off,
               ret);
    return ret;
}
MSH_CMD_EXPORT(cmd_canm_pair, configure seq-matched TX to RX latency tracking);
MSH_CMD_EXPORT_ALIAS(cmd_canm_pair, canm_pair, configure seq-matched TX to RX latency tracking);

static int cmd_canm_default(int argc, char **argv)
{
    RT_UNUSED(argc);
    RT_UNUSED(argv);

    can_metrics_set_bitrate(CANM_DEFAULT_BITRATE);
    (void)canm_seq_config(0x7C1U, RT_CAN_STDID, 1U);
    (void)canm_pair_config(0x7C0U, RT_CAN_STDID, 1U, 0x7C1U, RT_CAN_STDID, 1U);
    rt_kprintf("canm_default: bitrate=1000000 seq=0x7C1[1] pair=0x7C0[1]->0x7C1[1]\n");
    return 0;
}
MSH_CMD_EXPORT(cmd_canm_default, configure project CAN metric defaults);
MSH_CMD_EXPORT_ALIAS(cmd_canm_default, canm_default, configure project CAN metric defaults);
