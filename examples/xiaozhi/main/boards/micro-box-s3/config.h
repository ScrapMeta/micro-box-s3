// SPDX-License-Identifier: MIT
#pragma once
#include "micro_box_s3.h"
#define DISPLAY_WIDTH 160
#define DISPLAY_HEIGHT 160
#define CODEC_TX_GPIO GPIO_NUM_45
#define CODEC_RX_GPIO GPIO_NUM_48
static_assert(DISPLAY_WIDTH == MICRO_BOX_S3_LCD_WIDTH);
static_assert(DISPLAY_HEIGHT == MICRO_BOX_S3_LCD_HEIGHT);
static_assert(CODEC_TX_GPIO == MICRO_BOX_S3_AUDIO_TX);
static_assert(CODEC_RX_GPIO == MICRO_BOX_S3_AUDIO_RX);
