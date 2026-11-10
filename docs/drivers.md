# 驱动说明

| 驱动 | 接口 | 说明 |
|---|---|---|
| 开发板 | `micro_box_s3.h` | 双屏、相机和音频引脚定义 |
| 双屏 | `micro_box_s3_lcd_init()` | 屏0/1分别初始化SPI3/SPI2 |
| 相机 | `micro_box_s3_camera_config()` | RGB565、VGA、PSRAM单帧缓冲 |
| 音频 | `vb6824.h` | UART 2 Mbaud；输入OPUS，输出16 kHz单声道16-bit PCM |
| 本地输入 | `micro_box_s3_inputs.h` | GPIO11单触摸、GPIO12/13双按键，事件/快照 |
| 震动 | `micro_box_s3_motor.h` | GPIO14限时PWM，默认关闭，Timer1/Channel1 |

## 显示

```c
esp_lcd_panel_handle_t panel;
esp_lcd_panel_io_handle_t io;
ESP_ERROR_CHECK(micro_box_s3_lcd_init(0, &panel, &io));
```

160×160使用独立初始化序列、RGB顺序和关闭反色配置，不要只修改分辨率。DMA提交后，颜色缓冲必须保持有效到传输完成；显示例程用回调和信号量等待。

## 音频

初始化TX45/RX48后启用输入/输出并注册语音命令回调。`vb6824_audio_read()`返回OPUS数据，不能直接当PCM播放；`vb6824_audio_write()`输出PCM。

本仓库不启用硬件OPUS解码，不包含VB6824芯片升级或自动升级服务；小智例程的ESP32应用OTA另见其说明。AEC、双讲打断需要独立声学和服务端验收。

## 相机与本地控制

每次`esp_camera_fb_get()`成功后必须调用`esp_camera_fb_return()`，初始化成功不等于视觉实测通过。相机XCLK占Timer0/Channel0，震动占Timer1/Channel1。

触摸仅GPIO11，GPIO12/13配置机械按键，GPIO14保留模块IN，不再旧四路混扫。输入create后异步校准约3秒，手离开电极；输入事件回调不得阻塞。马达pulse校验时长/占空比/起动段，忙时拒绝，停止后冷却3秒。API、初始化/释放和接线限制见 [本地输入与震动](controls.md)，具体线程/资源约束以公共头文件为准。
