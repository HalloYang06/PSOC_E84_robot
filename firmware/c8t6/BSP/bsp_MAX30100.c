#include "bsp_MAX30100.h"

enum
{
    MAX30100_REG_INT_STATUS = 0x00,
    MAX30100_REG_INT_ENABLE = 0x01,
    MAX30100_REG_FIFO_WR_PTR = 0x02,
    MAX30100_REG_FIFO_OVF = 0x03,
    MAX30100_REG_FIFO_RD_PTR = 0x04,
    MAX30100_REG_FIFO_DATA = 0x05,
    MAX30100_REG_MODE_CONFIG = 0x06,
    MAX30100_REG_SPO2_CONFIG = 0x07,
    MAX30100_REG_LED_CONFIG = 0x09,
    MAX30100_REG_PART_ID = 0xFF
};

static I2C_HandleTypeDef *s_hi2c;

static int32_t max30100_write_reg(uint8_t reg, uint8_t value)
{
    HAL_StatusTypeDef rc;
    rc = HAL_I2C_Mem_Write(s_hi2c,
                           (uint16_t)(MAX30100_I2C_ADDR_7BIT << 1U),
                           reg,
                           I2C_MEMADD_SIZE_8BIT,
                           &value,
                           1U,
                           10U);
    return (rc == HAL_OK) ? 0 : -1;
}

static int32_t max30100_read_reg(uint8_t reg, uint8_t *value)
{
    HAL_StatusTypeDef rc;
    rc = HAL_I2C_Mem_Read(s_hi2c,
                          (uint16_t)(MAX30100_I2C_ADDR_7BIT << 1U),
                          reg,
                          I2C_MEMADD_SIZE_8BIT,
                          value,
                          1U,
                          10U);
    return (rc == HAL_OK) ? 0 : -1;
}

int32_t bsp_max30100_soft_reset(void)
{
    if (s_hi2c == 0)
    {
        return -1;
    }

    /* 写 MODE_CONFIG 的 RESET 位，等待芯片内部状态机恢复。 */
    if (max30100_write_reg(MAX30100_REG_MODE_CONFIG, 0x40U) != 0)
    {
        return -1;
    }
    HAL_Delay(2U);
    return 0;
}

int32_t bsp_max30100_init(I2C_HandleTypeDef *hi2c)
{
    uint8_t temp;
    uint8_t part_id;

    if (hi2c == 0)
    {
        return -1;
    }
    s_hi2c = hi2c;

    if (bsp_max30100_soft_reset() != 0)
    {
        return -1;
    }

    if (max30100_read_reg(MAX30100_REG_PART_ID, &part_id) != 0)
    {
        return -1;
    }
    if (part_id != MAX30100_EXPECTED_PART_ID)
    {
        return -1;
    }

    /* 按手册建议先清 FIFO 指针，再配置采样模式，避免上电脏数据影响首帧。 */
    if (max30100_write_reg(MAX30100_REG_FIFO_WR_PTR, 0x00U) != 0)
    {
        return -1;
    }
    if (max30100_write_reg(MAX30100_REG_FIFO_RD_PTR, 0x00U) != 0)
    {
        return -1;
    }
    if (max30100_write_reg(MAX30100_REG_FIFO_OVF, 0x00U) != 0)
    {
        return -1;
    }

    /* SpO2+HR 模式、100Hz、1600us、16bit 高精度。 */
    if (max30100_write_reg(MAX30100_REG_INT_ENABLE, 0x10U) != 0)
    {
        return -1;
    }
    if (max30100_write_reg(MAX30100_REG_SPO2_CONFIG, 0x47U) != 0)
    {
        return -1;
    }
    if (max30100_write_reg(MAX30100_REG_LED_CONFIG, 0x77U) != 0)
    {
        return -1;
    }
    if (max30100_write_reg(MAX30100_REG_MODE_CONFIG, 0x03U) != 0)
    {
        return -1;
    }

    (void)max30100_read_reg(MAX30100_REG_INT_STATUS, &temp);
    return 0;
}

int32_t bsp_max30100_read_sample(uint16_t *ir, uint16_t *red)
{
    uint8_t data[4];
    uint8_t wr_ptr;
    uint8_t rd_ptr;
    uint8_t available;
    HAL_StatusTypeDef rc;

    if ((s_hi2c == 0) || (ir == 0) || (red == 0))
    {
        return -1;
    }

    if (max30100_read_reg(MAX30100_REG_FIFO_WR_PTR, &wr_ptr) != 0)
    {
        return -1;
    }
    if (max30100_read_reg(MAX30100_REG_FIFO_RD_PTR, &rd_ptr) != 0)
    {
        return -1;
    }

    available = (uint8_t)((wr_ptr - rd_ptr) & 0x0FU);
    if (available == 0U)
    {
        return 1;
    }

    rc = HAL_I2C_Mem_Read(s_hi2c,
                          (uint16_t)(MAX30100_I2C_ADDR_7BIT << 1U),
                          MAX30100_REG_FIFO_DATA,
                          I2C_MEMADD_SIZE_8BIT,
                          data,
                          4U,
                          10U);
    if (rc != HAL_OK)
    {
        return -1;
    }

    /* FIFO 原始值按 16bit 左对齐输出，先不做位宽裁剪，交给上层滤波链处理。 */
    *ir = (uint16_t)(((uint16_t)data[0] << 8U) | data[1]);
    *red = (uint16_t)(((uint16_t)data[2] << 8U) | data[3]);
    return 0;
}
