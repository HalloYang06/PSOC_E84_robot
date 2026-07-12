#include <stdint.h>

#include "can_proto.h"
#include "data_fusion.h"

#define CHECK(expr)       \
    do                    \
    {                     \
        if (!(expr))      \
        {                 \
            return __LINE__; \
        }                 \
    } while (0)

int main(void)
{
    data_fusion_t fusion;
    fusion_snapshot_t snapshot;
    can_message_t message;
    const uint16_t samples[FUSION_ADC_CHANNEL_COUNT] = {
        0x0123U,
        0x0456U,
        0x0789U,
        0x0ABCU,
    };

    data_fusion_init(&fusion);
    data_fusion_update_adc4(&fusion, 99U, samples);

    CHECK(data_fusion_get_snapshot(&fusion, &snapshot));
    CHECK(snapshot.timestamp_ms == 99U);
    CHECK(snapshot.adc_valid == 1U);
    CHECK(snapshot.adc_raw[0] == 0x0123U);
    CHECK(snapshot.adc_raw[1] == 0x0456U);
    CHECK(snapshot.adc_raw[2] == 0x0789U);
    CHECK(snapshot.adc_raw[3] == 0x0ABCU);

    CHECK(can_proto_encode_sensor(&snapshot, &message) == 0);
    CHECK(message.id == F103_CAN_ID_SENSOR_TX);
    CHECK(message.dlc == 8U);
    CHECK(message.data[0] == 0x23U);
    CHECK(message.data[1] == 0x01U);
    CHECK(message.data[2] == 0x56U);
    CHECK(message.data[3] == 0x04U);
    CHECK(message.data[4] == 0x89U);
    CHECK(message.data[5] == 0x07U);
    CHECK(message.data[6] == 0xBCU);
    CHECK(message.data[7] == 0x0AU);

    return 0;
}
