# 例程与构建

使用已导出的ESP-IDF 5.4.3环境。

```bash
python -m unittest discover -s tests -v
python tools/build.py all --jobs 4
```

## 外设例程

| 目标 | 命令 | 行为 |
|---|---|---|
| display | `python tools/build.py display` | 双屏循环红、绿、蓝 |
| audio | `python tools/build.py audio` | 输出测试音，记录唤醒命令；输入为OPUS |
| camera | `python tools/build.py camera` | 每秒捕获一帧，打印尺寸与字节数 |
| touch | `python tools/build.py touch` | 打印四通道按下、松开、长按 |

四个目标使用同一个外设工程、互斥配置；编译一个不代表其他目标已编译或实测。

## 小智例程

```bash
python tools/build.py xiaozhi
```

板型名称固定为`micro-box-s3`，使用160×160眼睛素材、VB6824 UART音频和OV3660相机。首次运行按设备提示完成Wi-Fi配网和服务绑定。服务连接、账号绑定、AEC、在线对话和视觉识别须单独验收。

## 手动烧录

先识别串口、芯片和Flash容量并保存完整备份，再使用同一目标生成的`flasher_args.json`。应用镜像不是从0x00开始的合并镜像，不要把单独应用写到0x00，不要无故整片擦除。构建脚本只编译，不自动烧录。
