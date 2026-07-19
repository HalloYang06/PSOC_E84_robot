#include "app_ble_protocol.h"

#include <limits.h>
#include <string.h>

#define JSMN_PARENT_LINKS
#define JSMN_STATIC
#define JSMN_STRICT
#include "jsmn.h"

#define FIELD_SCHEMA (1u << 0)
#define FIELD_TYPE (1u << 1)
#define FIELD_REQUEST_ID (1u << 2)
#define FIELD_MODE (1u << 3)
#define FIELD_JOINT_MASK (1u << 4)
#define FIELD_TTL_MS (1u << 5)
#define FIELD_PROFILE (1u << 6)

static int is_json_space(uint8_t byte)
{
    return (byte == ' ') || (byte == '\t') || (byte == '\r') ||
           (byte == '\n');
}

static size_t skip_space(const uint8_t *frame, size_t length, size_t offset)
{
    while ((offset < length) && is_json_space(frame[offset]))
    {
        offset++;
    }
    return offset;
}

static int utf8_is_valid(const uint8_t *data, size_t length)
{
    size_t i = 0u;

    while (i < length)
    {
        uint8_t c = data[i++];
        if (c <= 0x7Fu)
        {
            continue;
        }
        if ((c >= 0xC2u) && (c <= 0xDFu))
        {
            if ((i >= length) || ((data[i] & 0xC0u) != 0x80u))
            {
                return 0;
            }
            i++;
            continue;
        }
        if ((c >= 0xE0u) && (c <= 0xEFu))
        {
            uint8_t c1;
            uint8_t c2;
            if ((length - i) < 2u)
            {
                return 0;
            }
            c1 = data[i];
            c2 = data[i + 1u];
            if (((c1 & 0xC0u) != 0x80u) || ((c2 & 0xC0u) != 0x80u) ||
                ((c == 0xE0u) && (c1 < 0xA0u)) ||
                ((c == 0xEDu) && (c1 > 0x9Fu)))
            {
                return 0;
            }
            i += 2u;
            continue;
        }
        if ((c >= 0xF0u) && (c <= 0xF4u))
        {
            uint8_t c1;
            uint8_t c2;
            uint8_t c3;
            if ((length - i) < 3u)
            {
                return 0;
            }
            c1 = data[i];
            c2 = data[i + 1u];
            c3 = data[i + 2u];
            if (((c1 & 0xC0u) != 0x80u) || ((c2 & 0xC0u) != 0x80u) ||
                ((c3 & 0xC0u) != 0x80u) ||
                ((c == 0xF0u) && (c1 < 0x90u)) ||
                ((c == 0xF4u) && (c1 > 0x8Fu)))
            {
                return 0;
            }
            i += 3u;
            continue;
        }
        return 0;
    }
    return 1;
}

static int token_is_plain_string(const uint8_t *frame, const jsmntok_t *token)
{
    int i;

    if ((token->type != JSMN_STRING) || (token->start < 0) ||
        (token->end < token->start))
    {
        return 0;
    }
    for (i = token->start; i < token->end; i++)
    {
        if ((frame[i] < 0x20u) || (frame[i] == '\\'))
        {
            return 0;
        }
    }
    return 1;
}

static int token_equals(const uint8_t *frame, const jsmntok_t *token,
                        const char *expected)
{
    size_t expected_length = strlen(expected);
    size_t token_length;

    if (!token_is_plain_string(frame, token))
    {
        return 0;
    }
    token_length = (size_t)(token->end - token->start);
    return (token_length == expected_length) &&
           (memcmp(frame + token->start, expected, expected_length) == 0);
}

static int parse_u32(const uint8_t *frame, const jsmntok_t *token,
                     uint32_t *out_value)
{
    uint32_t value = 0u;
    int i;

    if ((token->type != JSMN_PRIMITIVE) || (token->start < 0) ||
        (token->end <= token->start))
    {
        return 0;
    }
    if (((token->end - token->start) > 1) && (frame[token->start] == '0'))
    {
        return 0;
    }
    for (i = token->start; i < token->end; i++)
    {
        uint8_t byte = frame[i];
        uint32_t digit;
        if ((byte < '0') || (byte > '9'))
        {
            return 0;
        }
        digit = (uint32_t)(byte - '0');
        if (value > ((UINT32_MAX - digit) / 10u))
        {
            return 0;
        }
        value = (value * 10u) + digit;
    }
    *out_value = value;
    return 1;
}

static int verify_flat_object(const uint8_t *frame, size_t length,
                              const jsmntok_t *tokens, int token_count)
{
    size_t offset = skip_space(frame, length, 0u);
    int pairs;
    int pair;

    if ((token_count < 1) || (tokens[0].type != JSMN_OBJECT) ||
        (offset >= length) || (frame[offset] != '{'))
    {
        return 0;
    }
    pairs = tokens[0].size;
    if ((pairs < 1) || (token_count != (1 + (pairs * 2))))
    {
        return 0;
    }
    offset++;
    for (pair = 0; pair < pairs; pair++)
    {
        const jsmntok_t *key = &tokens[1 + (pair * 2)];
        const jsmntok_t *value = &tokens[2 + (pair * 2)];

        offset = skip_space(frame, length, offset);
        if ((key->type != JSMN_STRING) || (key->parent != 0) ||
            (offset >= length) || (frame[offset] != '"') ||
            ((size_t)key->start != offset + 1u))
        {
            return 0;
        }
        offset = (size_t)key->end + 1u;
        offset = skip_space(frame, length, offset);
        if ((offset >= length) || (frame[offset] != ':') ||
            (value->parent != 1 + (pair * 2)))
        {
            return 0;
        }
        offset = skip_space(frame, length, offset + 1u);
        if (value->type == JSMN_STRING)
        {
            if ((offset >= length) || (frame[offset] != '"') ||
                ((size_t)value->start != offset + 1u))
            {
                return 0;
            }
            offset = (size_t)value->end + 1u;
        }
        else if (value->type == JSMN_PRIMITIVE)
        {
            if ((size_t)value->start != offset)
            {
                return 0;
            }
            offset = (size_t)value->end;
        }
        else
        {
            return 0;
        }
        offset = skip_space(frame, length, offset);
        if (pair + 1 < pairs)
        {
            if ((offset >= length) || (frame[offset] != ','))
            {
                return 0;
            }
            offset++;
        }
        else if ((offset >= length) || (frame[offset] != '}'))
        {
            return 0;
        }
    }
    offset = skip_space(frame, length, offset + 1u);
    return offset == length;
}

static uint32_t field_bit(const uint8_t *frame, const jsmntok_t *key)
{
    if (token_equals(frame, key, "schema"))
    {
        return FIELD_SCHEMA;
    }
    if (token_equals(frame, key, "type"))
    {
        return FIELD_TYPE;
    }
    if (token_equals(frame, key, "request_id"))
    {
        return FIELD_REQUEST_ID;
    }
    if (token_equals(frame, key, "mode"))
    {
        return FIELD_MODE;
    }
    if (token_equals(frame, key, "joint_mask"))
    {
        return FIELD_JOINT_MASK;
    }
    if (token_equals(frame, key, "ttl_ms"))
    {
        return FIELD_TTL_MS;
    }
    if (token_equals(frame, key, "profile"))
    {
        return FIELD_PROFILE;
    }
    return 0u;
}

static int parse_type(const uint8_t *frame, const jsmntok_t *token,
                      app_ble_request_type_t *out_type)
{
    if (token_equals(frame, token, "heartbeat"))
    {
        *out_type = APP_BLE_REQUEST_HEARTBEAT;
        return 1;
    }
    if (token_equals(frame, token, "mode_request"))
    {
        *out_type = APP_BLE_REQUEST_MODE;
        return 1;
    }
    if (token_equals(frame, token, "training_request"))
    {
        *out_type = APP_BLE_REQUEST_TRAINING;
        return 1;
    }
    if (token_equals(frame, token, "stop_request"))
    {
        *out_type = APP_BLE_REQUEST_STOP;
        return 1;
    }
    return 0;
}

static int parse_training(const uint8_t *frame, const jsmntok_t *token,
                          app_ble_training_t *out_training)
{
    if (token_equals(frame, token, "single_joint_curl_j5_v1"))
    {
        *out_training = APP_BLE_TRAINING_CURL_J5;
        return 1;
    }
    if (token_equals(frame, token, "fixed_elbow_flex_extend_v1"))
    {
        *out_training = APP_BLE_TRAINING_FIXED_ELBOW_FLEX_EXTEND;
        return 1;
    }
    if (token_equals(frame, token, "fixed_shoulder_planar_v1"))
    {
        *out_training = APP_BLE_TRAINING_FIXED_SHOULDER_PLANAR;
        return 1;
    }
    if (token_equals(frame, token, "fixed_coordinated_elbow_shoulder_v1"))
    {
        *out_training = APP_BLE_TRAINING_FIXED_COORDINATED;
        return 1;
    }
    if (token_equals(frame, token, "fixed_shoulder_fore_aft_v1"))
    {
        *out_training = APP_BLE_TRAINING_FIXED_SHOULDER_FORE_AFT;
        return 1;
    }
    return 0;
}

static uint8_t training_joint_mask(app_ble_training_t training)
{
    switch (training)
    {
    case APP_BLE_TRAINING_CURL_J5:
    case APP_BLE_TRAINING_FIXED_ELBOW_FLEX_EXTEND:
        return APP_BLE_PROTOCOL_FIXED_ELBOW_MASK;
    case APP_BLE_TRAINING_FIXED_SHOULDER_PLANAR:
        return APP_BLE_PROTOCOL_FIXED_SHOULDER_PLANAR_MASK;
    case APP_BLE_TRAINING_FIXED_COORDINATED:
        return APP_BLE_PROTOCOL_FIXED_COORDINATED_MASK;
    default:
        return 0u;
    }
}

static int parse_mode(const uint8_t *frame, const jsmntok_t *token,
                      app_ble_mode_t *out_mode)
{
    if (token_equals(frame, token, "active"))
    {
        *out_mode = APP_BLE_MODE_ACTIVE;
        return 1;
    }
    if (token_equals(frame, token, "assist"))
    {
        *out_mode = APP_BLE_MODE_ASSIST;
        return 1;
    }
    if (token_equals(frame, token, "resist"))
    {
        *out_mode = APP_BLE_MODE_RESIST;
        return 1;
    }
    return 0;
}

app_ble_protocol_result_t app_ble_protocol_parse(const uint8_t *frame,
                                                 size_t length,
                                                 app_ble_request_t *out_request)
{
    jsmntok_t tokens[APP_BLE_PROTOCOL_TOKEN_LIMIT];
    app_ble_request_t request = {0};
    jsmn_parser parser;
    uint32_t fields = 0u;
    uint32_t number;
    int token_count;
    int pair;

    if (out_request == NULL)
    {
        return APP_BLE_PROTOCOL_INVALID;
    }
    memset(out_request, 0, sizeof(*out_request));
    if ((frame == NULL) || (length == 0u) ||
        (length > APP_BLE_PROTOCOL_MAX_FRAME_BYTES) ||
        !utf8_is_valid(frame, length))
    {
        return APP_BLE_PROTOCOL_INVALID;
    }

    jsmn_init(&parser);
    token_count = jsmn_parse(&parser, (const char *)frame, length, tokens,
                             APP_BLE_PROTOCOL_TOKEN_LIMIT);
    if ((token_count < 0) ||
        !verify_flat_object(frame, length, tokens, token_count))
    {
        return APP_BLE_PROTOCOL_INVALID;
    }

    for (pair = 0; pair < tokens[0].size; pair++)
    {
        const jsmntok_t *key = &tokens[1 + (pair * 2)];
        const jsmntok_t *value = &tokens[2 + (pair * 2)];
        uint32_t bit = field_bit(frame, key);

        if ((bit == 0u) || ((fields & bit) != 0u) ||
            !token_is_plain_string(frame, key))
        {
            return APP_BLE_PROTOCOL_INVALID;
        }
        fields |= bit;
        switch (bit)
        {
        case FIELD_SCHEMA:
            if (!token_equals(frame, value, "rehab_ble_v1"))
            {
                return APP_BLE_PROTOCOL_INVALID;
            }
            break;
        case FIELD_TYPE:
            if (!parse_type(frame, value, &request.type))
            {
                return APP_BLE_PROTOCOL_INVALID;
            }
            break;
        case FIELD_REQUEST_ID:
            if (!parse_u32(frame, value, &request.request_id) ||
                (request.request_id == 0u))
            {
                return APP_BLE_PROTOCOL_INVALID;
            }
            break;
        case FIELD_MODE:
            if (!parse_mode(frame, value, &request.mode))
            {
                return APP_BLE_PROTOCOL_INVALID;
            }
            break;
        case FIELD_JOINT_MASK:
            if (!parse_u32(frame, value, &number) ||
                ((number != APP_BLE_PROTOCOL_REHAB_MASK) &&
                 (number != APP_BLE_PROTOCOL_FIXED_ELBOW_MASK) &&
                 (number != APP_BLE_PROTOCOL_FIXED_SHOULDER_PLANAR_MASK) &&
                 (number != APP_BLE_PROTOCOL_FIXED_COORDINATED_MASK)))
            {
                return APP_BLE_PROTOCOL_INVALID;
            }
            request.joint_mask = (uint8_t)number;
            break;
        case FIELD_TTL_MS:
            if (!parse_u32(frame, value, &request.ttl_ms) ||
                (request.ttl_ms < APP_BLE_PROTOCOL_MIN_TTL_MS) ||
                (request.ttl_ms > APP_BLE_PROTOCOL_MAX_TTL_MS))
            {
                return APP_BLE_PROTOCOL_INVALID;
            }
            break;
        case FIELD_PROFILE:
            if (!parse_training(frame, value, &request.training))
            {
                return APP_BLE_PROTOCOL_INVALID;
            }
            break;
        default:
            return APP_BLE_PROTOCOL_INVALID;
        }
    }

    if (request.type == APP_BLE_REQUEST_MODE)
    {
        if (fields != (FIELD_SCHEMA | FIELD_TYPE | FIELD_REQUEST_ID |
                       FIELD_MODE | FIELD_JOINT_MASK | FIELD_TTL_MS) ||
            (request.joint_mask != APP_BLE_PROTOCOL_REHAB_MASK))
        {
            return APP_BLE_PROTOCOL_INVALID;
        }
    }
    else if (request.type == APP_BLE_REQUEST_TRAINING)
    {
        uint8_t expected_mask = training_joint_mask(request.training);

        if (fields != (FIELD_SCHEMA | FIELD_TYPE | FIELD_REQUEST_ID |
                       FIELD_PROFILE | FIELD_JOINT_MASK | FIELD_TTL_MS) ||
            (expected_mask == 0u) ||
            (request.joint_mask != expected_mask))
        {
            return APP_BLE_PROTOCOL_INVALID;
        }
    }
    else if ((request.type == APP_BLE_REQUEST_HEARTBEAT) ||
             (request.type == APP_BLE_REQUEST_STOP))
    {
        if (fields != (FIELD_SCHEMA | FIELD_TYPE | FIELD_REQUEST_ID))
        {
            return APP_BLE_PROTOCOL_INVALID;
        }
    }
    else
    {
        return APP_BLE_PROTOCOL_INVALID;
    }

    *out_request = request;
    return APP_BLE_PROTOCOL_OK;
}
