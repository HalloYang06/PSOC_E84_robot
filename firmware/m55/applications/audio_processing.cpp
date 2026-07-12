#include "audio_processing.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define PI 3.14159265358979323846f
#define SAMPLE_RATE 16000
#define MEL_FMIN 125.0f
#define MEL_FMAX 7500.0f
#define EPSILON 1.0e-6f
#define TOP_DB 80.0f

bool AudioProcessing_Init(void)
{
    printf("Audio processing initialized\n");
    return true;
}

void AudioProcessing_PreEmphasis(const int16_t *input,
                                 float *output,
                                 int length,
                                 float coeff)
{
    if ((input == nullptr) || (output == nullptr) || (length <= 0))
    {
        return;
    }

    output[0] = (float)input[0];
    for (int i = 1; i < length; i++)
    {
        output[i] = (float)input[i] - coeff * (float)input[i - 1];
    }
}

static void apply_hann_window(float *frame, int frame_size)
{
    for (int i = 0; i < frame_size; i++)
    {
        float window = 0.5f - 0.5f * cosf(2.0f * PI * i / (frame_size - 1));
        frame[i] *= window;
    }
}

static float hz_to_mel(float hz)
{
    return 2595.0f * log10f(1.0f + hz / 700.0f);
}

static float mel_to_hz(float mel)
{
    return 700.0f * (powf(10.0f, mel / 2595.0f) - 1.0f);
}

static void compute_power_spectrum(const float *input, float *power_spectrum, int fft_size)
{
    for (int k = 0; k < fft_size / 2; k++)
    {
        float real = 0.0f;
        float imag = 0.0f;

        for (int n = 0; n < fft_size; n++)
        {
            float angle = 2.0f * PI * (float)(k * n) / (float)fft_size;
            real += input[n] * cosf(angle);
            imag -= input[n] * sinf(angle);
        }

        power_spectrum[k] = real * real + imag * imag;
    }
}

static void apply_mel_filterbank(const float *power_spectrum, float *mel_energies)
{
    int bins[N_MEL_FILTERS + 2];
    const float mel_min = hz_to_mel(MEL_FMIN);
    const float mel_max = hz_to_mel(MEL_FMAX);

    for (int i = 0; i < N_MEL_FILTERS + 2; i++)
    {
        float mel = mel_min + ((mel_max - mel_min) * (float)i) / (float)(N_MEL_FILTERS + 1);
        float hz = mel_to_hz(mel);
        int bin = (int)floorf(((float)FFT_SIZE + 1.0f) * hz / (float)SAMPLE_RATE);

        if (bin < 0)
        {
            bin = 0;
        }
        else if (bin > (FFT_SIZE / 2 - 1))
        {
            bin = FFT_SIZE / 2 - 1;
        }

        bins[i] = bin;
    }

    for (int m = 0; m < N_MEL_FILTERS; m++)
    {
        float mel_energy = 0.0f;
        int left = bins[m];
        int center = bins[m + 1];
        int right = bins[m + 2];

        if (center <= left)
        {
            center = left + 1;
        }
        if (right <= center)
        {
            right = center + 1;
        }

        for (int k = left; k < center && k < FFT_SIZE / 2; k++)
        {
            float weight = (float)(k - left) / (float)(center - left);
            mel_energy += power_spectrum[k] * weight;
        }

        for (int k = center; k < right && k < FFT_SIZE / 2; k++)
        {
            float weight = (float)(right - k) / (float)(right - center);
            mel_energy += power_spectrum[k] * weight;
        }

        mel_energies[m] = 10.0f * log10f(mel_energy + EPSILON);
    }
}

static void normalize_features(float *features, int length)
{
    float mean = 0.0f;
    float variance = 0.0f;

    if ((features == nullptr) || (length <= 0))
    {
        return;
    }

    for (int i = 0; i < length; i++)
    {
        mean += features[i];
    }
    mean /= (float)length;

    for (int i = 0; i < length; i++)
    {
        float diff = features[i] - mean;
        variance += diff * diff;
    }
    variance /= (float)length;

    {
        float std = sqrtf(variance) + EPSILON;
        for (int i = 0; i < length; i++)
        {
            features[i] = (features[i] - mean) / std;
        }
    }
}

static void power_to_db_relative(float *features, int length)
{
    float max_value = features[0];
    float min_allowed;

    for (int i = 1; i < length; i++)
    {
        if (features[i] > max_value)
        {
            max_value = features[i];
        }
    }

    min_allowed = max_value - TOP_DB;
    for (int i = 0; i < length; i++)
    {
        if (features[i] < min_allowed)
        {
            features[i] = min_allowed;
        }
    }
}

bool AudioProcessing_ExtractMFCC(const int16_t *audio_data,
                                 int audio_len,
                                 float *mfcc_output,
                                 int n_frames,
                                 int n_mfcc)
{
    if ((audio_data == nullptr) || (mfcc_output == nullptr) || (n_mfcc != N_MEL_FILTERS))
    {
        return false;
    }

    memset(mfcc_output, 0, sizeof(float) * n_frames * n_mfcc);

    for (int frame_idx = 0; frame_idx < n_frames; frame_idx++)
    {
        int start = frame_idx * HOP_LENGTH;
        float frame[FFT_SIZE] = {0};
        float power_spectrum[FFT_SIZE / 2];
        float *feature_frame = mfcc_output + frame_idx * n_mfcc;

        if ((start + WINDOW_LENGTH) > audio_len)
        {
            break;
        }

        for (int i = 0; i < WINDOW_LENGTH; i++)
        {
            frame[i] = (float)audio_data[start + i];
        }

        apply_hann_window(frame, WINDOW_LENGTH);
        compute_power_spectrum(frame, power_spectrum, FFT_SIZE);
        apply_mel_filterbank(power_spectrum, feature_frame);
    }

    power_to_db_relative(mfcc_output, n_frames * n_mfcc);
    normalize_features(mfcc_output, n_frames * n_mfcc);
    return true;
}

void AudioProcessing_FrameWindow(const float *input,
                                 float *output,
                                 int frame_size,
                                 int hop_length,
                                 int n_frames)
{
    for (int i = 0; i < n_frames; i++)
    {
        int start = i * hop_length;
        float *frame = output + i * frame_size;

        memcpy(frame, input + start, frame_size * sizeof(float));
        apply_hann_window(frame, frame_size);
    }
}
