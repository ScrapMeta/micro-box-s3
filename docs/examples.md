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
| touch | `python tools/build.py touch` | GPIO11单触摸：按下、松开、长按及原始快照 |
| buttons | `python tools/build.py buttons` | GPIO12/13机械按键，独立消抖、按下/松开/长按 |
| motor | `python tools/build.py motor` | GPIO14模块IN：串口V请求200ms短振，X停止/S状态；无上电自动动作 |
| controls | `python tools/build.py controls` | 单触摸、双按键及手动串口马达入口，输入不自动触发震动 |

七个目标使用同一个外设工程、互斥配置，均初始化马达为idle；编译一个不代表其他目标已编译或实测。共享组件和接线见 [本地输入与震动](controls.md)。

## 小智例程

```bash
python tools/build.py xiaozhi
```

板型名称固定为`micro-box-s3`，使用160×160眼睛素材、VB6824 UART音频和OV3660相机。本地组件在网络等待前初始化，唯一GPIO11触摸、GPIO12/13双按键、GPIO14马达idle。只记录输入事件，不默认改变眼样式、清配网或触发震动。首次运行按提示配网/绑定；新组件集成、在线对话、AEC和视觉识别须独立验收。

## 独立历史诊断

统一入口也支持 `python tools/build.py controls-test`、`motor-test`、`motor-patterns`。它们分别保留输入原始诊断、单次200ms短振、六组时长/占空比的此前实测实现。马达均无上电自动序列；各例程限制见目录README。它们不复用本次新组件，因此历史实机通过不能自动升级为新组件或重编镜像的验收。

## 手动烧录

先识别串口、芯片和Flash容量并保存完整备份，再使用同一目标生成的`flasher_args.json`。应用镜像不是从0x00开始的合并镜像，不要把单独应用写到0x00，不要无故整片擦除。构建脚本只编译，不自动烧录。

只有当前引导程序、活动应用槽及伴随资源与新分区兼容，才允许仅写应用；写后独立回读并验证保留区域。本次工程更新不重刷设备，当前保留最近马达对比诊断固件，不能因本次构建成功就标为已烧录。
