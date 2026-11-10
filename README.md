# micro-box-s3

ESP32-S3 双屏语音视觉开发板的独立参考工程，统一使用名称 **micro-box-s3**。

阅读：[开发板](docs/board.md) · [接口与针序](docs/interfaces.md) · [本地输入与震动](docs/controls.md) · [驱动](docs/drivers.md) · [例程](docs/examples.md) · [验证记录](docs/validation.md)。

## 板级配置

| 项目 | 配置 |
|---|---|
| 主控 | ESP32-S3 |
| Flash | 16 MB，QIO，80 MHz |
| PSRAM | 8 MB，Octal，80 MHz |
| 双屏 | 0.71英寸，160×160，RGB565；GC9A01接口驱动，20 MHz |
| 音频 | VB6824，UART 2,000,000 baud |
| 摄像头 | OV3660，RGB565 VGA，PSRAM 单帧缓冲 |
| 本地输入 | 1路触摸GPIO11；按键A/B：GPIO12/13 |
| 震动 | GPIO14控制带驱动模块；默认关闭，VBAT供电须核验 |
| SDK | ESP-IDF 5.4.3 |

## 目录

- `board.json`：硬件能力与 GPIO 定义。
- `components/micro_box_s3`：开发板初始化库，提供双屏和摄像头配置。
- `components/micro_box_s3_controls`：单路触摸、双按键和有界时长PWM震动组件，事件与业务解耦。
- `components/esp_lcd_gc9a01`：160×160 SPI 屏驱动，包含该尺寸所需初始化流程。
- `components/vb6824`：UART 音频传输库，仅包含音频、唤醒词和音量接口；不包含芯片升级网络服务。
- `examples/peripherals`：显示、音频、相机、单触摸、双按键、马达和组合controls七个互斥模式。
- `examples/controls-test`、`motor-test`、`motor-patterns`：此前独立实测诊断，保留重现入口，不等于新组件已实机验收。
- `examples/xiaozhi`：小智语音视觉例程，保留双眼动画、语音唤醒、摄像头多模态和配网流程。
- `tools/build.py`：隔离构建脚本。只编译和生成镜像，不打开串口，不自动烧录。
- `tests`：真实host C行为测试及配置/集成契约测试。
- `docs`：硬件、驱动和例程说明。

## 快速开始

在已导出 ESP-IDF 5.4.3 环境后：

```bash
python tools/build.py display
python tools/build.py audio
python tools/build.py camera
python tools/build.py touch
python tools/build.py buttons
python tools/build.py motor
python tools/build.py controls
python tools/build.py xiaozhi
```

构建目录位于 `.build/<target>/`。每个目标单独生成 `sdkconfig`、日志和 `result.json`；脚本不会执行 `flash`。

烧录前必须确认：

1. 目标设备确实是 ESP32-S3，并核对 Flash 容量。
2. 设备使用本目录对应的 160×160 双屏接线。
3. `result.json` 中的偏移、镜像和哈希与待烧录文件一致。
4. 保留当前设备完整备份。

## 实机验收状态

此前小智版本已完成烧录、回读及双眼/提示音基础验收，见 [历史实机记录](docs/device-test.md)。单触摸和双按键的独立诊断已观察到基本事件；马达独立诊断已通过 [时长/占空比对比](docs/motor-patterns.md)。本次新共享组件及小智本地输入适配尚未刷机，不继承历史实机通过；当前设备保留最近的马达对比诊断固件。

## 许可

本仓库保留现有软件的许可和版权声明。根目录 `LICENSE` 为 MIT；屏驱动附带 Apache-2.0 许可文本。各组件的许可证以组件目录文件为准。

本仓库不分发完整 Flash 备份、账号信息、设备绑定状态或预编译语音芯片升级库。