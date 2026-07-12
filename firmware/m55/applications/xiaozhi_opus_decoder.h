#ifndef XIAOZHI_OPUS_DECODER_H
#define XIAOZHI_OPUS_DECODER_H

#include <rtthread.h>
#include <stdint.h>

rt_err_t xiaozhi_opus_decoder_init(void);
rt_err_t xiaozhi_opus_decoder_configure(int sample_rate, int channels);
rt_err_t xiaozhi_opus_decoder_reset(void);
int xiaozhi_opus_decoder_sample_rate(void);
rt_err_t xiaozhi_opus_decoder_decode(const uint8_t *packet,
                                     rt_size_t packet_len,
                                     int16_t *pcm_out,
                                     rt_size_t pcm_out_cap_samples,
                                     rt_size_t *pcm_out_samples);
rt_err_t xiaozhi_opus_encoder_init(void);
rt_err_t xiaozhi_opus_encoder_encode(const int16_t *pcm,
                                     rt_size_t pcm_samples,
                                     uint8_t *packet_out,
                                     rt_size_t packet_out_cap,
                                     rt_size_t *packet_out_len);
void xiaozhi_opus_decoder_deinit(void);
void xiaozhi_opus_encoder_deinit(void);

#endif
