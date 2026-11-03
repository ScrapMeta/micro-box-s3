# micro-box-s3 小智例程

面向 ESP32-S3 的独立 ESP-IDF 5.4.3 应用，固定单一 `micro-box-s3` 板型。入口是实际的 `app_main()` 和小智应用状态机，不是外设演示或空壳。

## 保留的功能

- 两路独立 SPI 的 160×160 双眼（GC9A01接口驱动）；保留原有 160×160 眼睛素材、瞳孔缩放、眨眼和情绪映射。一个动画帧同步送到两个显示面板。
- VB6824 UART 音频与本地语音指令：GPIO45 TX / GPIO48 RX，硬件编码 Opus 上行，软件 Opus 解码为 PCM 下行，中文唤醒词和“开始配网”。不包含语音芯片网络升级、升级网页、预编译升级库或升级服务连接。
- OV3660：RGB565 VGA、一个 PSRAM 帧缓冲；MCP 拍照工具、JPEG 编码和 multipart 图像解释上传。视觉地址及令牌通过服务端 MCP capabilities 提供。
- 小智 WebSocket 与 MQTT/UDP 音频协议、激活与服务发现。保留小智协议自己的 ESP32 应用 OTA；它与已移除的语音芯片升级是两件事。
- 中文 SoftAP 配网页面、中文语音及公共提示音。热点前缀为 `micro-box-s3`。未保存 Wi-Fi 或连接失败时自动进入配网；正常运行后也可说“开始配网”。
- 四路原有触摸交互；板级 GPIO/摄像头配置统一来自仓库公共组件，不在本例中再次分配 SPI 总线。

眼睛模式沿用直接 SPI 渲染，不显示 LVGL 聊天气泡或相机预览；拍照上传不依赖本地预览。未接出的背光调节和实体启动按钮不创建控制对象。

## 编译

先在 ESP-IDF **5.4.3** 的已激活终端执行：

```sh
cd examples/xiaozhi
idf.py set-target esp32s3
idf.py build
```

不要复用其它项目的 `sdkconfig` 或 `dependencies.lock`。首次配置由 Component Manager 解析精确版本依赖；需要注册表网络或完整本机缓存。生成的 `sdkconfig`、锁文件、`build/` 和 `managed_components/` 是本机产物，不随例程提交。

默认硬件参数：16 MB QIO Flash / 80 MHz，8 MB octal PSRAM / 80 MHz，240 MHz CPU。`partitions.csv` 使用两份 7 MiB 的 ESP32 应用分区，保留 NVS、OTA 数据及 PHY 初始化区；UART 唤醒不需要本地语音模型分区。

`idf.py menuconfig` 的 `micro-box-s3 Xiaozhi` 菜单可配置小智激活/服务发现地址；默认使用小智协议服务。板型、分辨率、中文、硬件 Opus 上行固定。`VB6824_OTA_SUPPORT` 为不可启用的隐藏配置，CMake 也会拒绝开启它的配置。

## 依赖

仓库公共组件通过可移植的 `../../components` 路径引用：

| 组件 | 用途 |
| --- | --- |
| `micro_box_s3` | 双屏 SPI 初始化、OV3660 引脚与帧缓冲配置 |
| `esp_lcd_gc9a01` | 160×160 LCD 驱动，由公共板级组件依赖 |
| `vb6824` | 纯 UART 源码接口，无网络升级实现 |

本例唯一内置的应用级组件是 `components/opus_codec`：源码版 2.3.1 C++ 封装，保留应用实际使用的 `OpusDecoderWrapper::Config()` 与重采样 API。没有复制其它 codec、开发板或托管组件目录。

注册表依赖均为精确版本：

| 组件 | 版本 | 用途 |
| --- | --- | --- |
| `78/esp-opus` | 1.0.5 | Opus 编解码及 SILK 重采样，内置封装的依赖 |
| `78/esp-wifi-connect` | 2.4.3 | Wi-Fi、中文 SoftAP 配网、SSID 保存 |
| `78/esp-ml307` | 2.1.6 | 复用其通用 HTTP/TLS、WebSocket、MQTT/UDP 抽象，不实例化蜂窝板型 |
| `78/xiaozhi-fonts` | 1.3.2 | 通用字体及图标接口兼容 |
| `espressif/esp32-camera` | 2.1.8 | OV3660 摄像头驱动 |
| `espressif/esp_jpeg` | 1.3.2 | 摄像头 JPEG 转换依赖 |
| `lvgl/lvgl` | 9.2.2 | 显示抽象与图像描述数据类型 |

语音芯片固件须匹配本例的输入编码、采样率及帧配置；在线音频帧兼容性仍需实测，本例不会更新该芯片固件。

## 文件清单

- `CMakeLists.txt`、`sdkconfig.defaults`、`partitions.csv`：标准 ESP-IDF 工程、硬件默认值与分区。
- `main/CMakeLists.txt`、`main/Kconfig.projbuild`、`main/idf_component.yml`：单板源文件清单、应用选项与精确依赖。
- `main/boards/micro-box-s3/{micro-box-s3.cc,config.h}`：唯一板型与公共 BSP 接入。
- `main/boards/common/`：必要的 Wi-Fi、板级抽象、相机、触摸及背光抽象；无其它板型或蜂窝板实现。
- `main/{application.*,main.cc,mcp_server.*,ota.*,settings.*,system_info.*,background_task.*}`：实际应用、MCP、协议服务发现和任务调度。
- `main/{audio_codecs,audio_processing,protocols,display,iot,led}/`：仅保留本板使用的接口与实现。
- `main/eye_data/160_160/`：160×160 素材；不含其它尺寸素材。
- `main/assets/{zh-CN,common}/` 与 `main/assets/lang_config.h`：中文、公共声音及对应固定资源声明；没有额外的构建期 Python 生成器。
- `components/opus_codec/`：源码封装、精确 manifest 和许可；SILK 文件保留其独立版权许可告知。
- `LICENSE`：保留 MIT 许可及 `Copyright (c) 2025 yichone`。
- 仓库 `tests/test_xiaozhi_contract.py`：单个静态集成契约。

## 验证边界与风险

运行仓库静态契约：

```sh
python -B -m unittest discover -s tests -p test_xiaozhi_contract.py -v
```

契约检查入口、单一板型、源码、配置、资源与MCP接口。完整构建结果及验收边界见[验证说明](../../docs/validation.md)。

摄像头、音频、网络和双屏并行时的内存余量，以及激活、在线音频、AEC和视觉能力，仍需独立硬件联调。
