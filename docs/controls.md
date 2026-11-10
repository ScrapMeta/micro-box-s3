# 本地输入与震动：1触摸、2按键、1马达

本工程当前固定分配为 **GPIO11 单路电容触摸、GPIO12/13 两个机械按键、GPIO14 震动模块 IN**。接口、板级头文件及组件保持同一分配，不再把GPIO12/13/14作为电容触摸通道扫描。

## 1. 接口与连接

以下为 **CN4原理图Pin编号**，不是从插头正面或反面看的左右顺序。实物版号、Pin1、插头方向与线序需断电确认，其他接口见 [接口手册](interfaces.md)。

| CN4 Pin | 网络 | 连接 | 软件模式 |
|---|---|---|---|
| 1 | GPIO11 / TP1 | 独立铜箔电极，只接一根信号线 | 原生电容触摸，唯一通道 |
| 2 | GPIO12 | 按键A一端，另一端接Pin6 | 输入上拉，低电平按下 |
| 3 | GPIO13 | 按键B一端，另一端接Pin6 | 输入上拉，低电平按下 |
| 4 | GPIO14 | 带驱动震动模块的IN | 高电平/PWM控制；不是马达功率输出 |
| 5 | VBAT | 模块VCC的候选供电 | 保护后电池供电路径、极性和载流需核验 |
| 6 | GND | 按键回线、模块地，与主控共地 | 电源/逻辑参考地 |

H1/H2与CN4共用相同GPIO，并非额外通道：H1.5=GPIO14、H1.6=GPIO13、H2.5=GPIO12、H2.6=GPIO11；H1/H2的1/2为GND，3/4为VBAT。不得同时接入争用相同脚的触摸、按键、舵机或其他输出。

板级单一来源为 `board.json` 与 `micro_box_s3_pins.h`。后者只含引脚/常量，可独立包含，不必为读取GPIO定义初始化相机或显示。

### 按键

使用无源、常开、自复位的瞬时触点；两脚带线款最直接。四脚轻触必须先断电测清内部触点分组。按键只短接对应GPIO与GND，不能接VBAT、5V；需要外部上拉时只可接已核验的3.3V逻辑电源。

两键可共用可靠的地线分支，但要和马达大电流回流分开布置。默认25ms消抖、2秒长按，按下/松开/长按分别上报；长按一次保持期间只上报一次。默认事件没有恢复出厂、清配网、开关电源等业务副作用。

### 触摸铜箔

只保留GPIO11。可用可焊接薄铜箔或柔性电极，圆角、绝缘覆盖、焊点与线缆拉力缓解；铜箔本身不接GND、3.3V或VBAT。信号引线尽量短，贴近实际毛绒外层内侧；面积/布厚/空气间隙和最终线长需实测，不能靠增大面积保证灵敏度。

启动后约3秒建立固定基线，校准时手离开电极。默认按下约为基线+10%，释放约为+5%，35ms状态消抖；这是诊断初值而非所有布层通用参数。可读取raw/基线/状态快照；触摸失效、校准未完成不作为按下证据。

### 端子与线材

CN4图纸标称MX1.25系列6P，购买配套母壳、金属端子和已压接线束；不能只凭“1.25mm/6P”宣称兼容。端子允许线规及绝缘外径必须匹配。信号支线可从细软多股线选起，马达供电线按实际启动/故障电流、线长及压降选择；不从图片推断马达模块排针间距。

## 2. 震动模块与供电

本项目连接的是 **IN/VCC/GND三针、已带驱动的震动马达模块**，不是裸电机。模块VCC不由GPIO供电，也不从麦克风或扬声器接口供电。不要额外叠加第二套功率驱动，除非具体电路确有需要。

用户图片标称工作3.0～5.3V、额定5V、启动3.7V、额定电流≤60mA、启动电流≤90mA。这些是商家说明，不是实测；3.7V启动电压不是IN逻辑阈值，≤90mA也不是堵转/短路设计上限。

普通单节锂电池的标称3.7V不是恒定电压。可优先验证保护后的VBAT直供模块，不能把“额定5V”解释为必须升压；但不保证低电量时可靠起振或恒定强度。以具体电池和保护规格为准，不把模块最低工作电压当作电芯安全截止电压。

CN4.5只有在当前板已确认VBAT来源、保护后属性、极性、走线/端子载流和压降满足要求时，才作为模块VCC。否则从确认的受保护供电入口分支。马达供电回流直接回电源公共地，避免经过触摸/按键长回线。USB充电同时带负载、额外电源并接和防反灌须另核。

IN仍须按实际模块核对3.3V高电平裕量、内部上拉/反灌、主控断电状态及默认关闭；一次实机成功不构成全电池电压下的电气兼容认证。软件关闭不能保证复位瞬间无物理毛刺，默认关闭还需硬件配合。

## 3. 可复用组件

`components/micro_box_s3_controls` 提供两个独立句柄接口：

| 头文件 | API | 职责 |
|---|---|---|
| `micro_box_s3_inputs.h` | `micro_box_s3_inputs_create/delete/get_snapshot` | 单触摸、双按键，异步校准/扫描与事件回调 |
| `micro_box_s3_motor.h` | `micro_box_s3_motor_create/pulse/stop/get_state/delete` | 有界时长PWM震动，无上电自动动作 |

输入组件与马达组件分别独占各自板级资源；不允许重复实例或另一个驱动同时初始化相同触摸硬件、GPIO或LEDC资源。输入create异步返回，按钮可先于触摸校准工作；事件回调可在create返回前运行，不得阻塞或在回调内删除自身。快照在短临界区内复制，必须同时检查 `touch_valid`，不能把失效样本期间保留的状态当作新按下证据。

两者的释放契约不同，均需所有者停止新的外部调用并串行管理句柄：

- 输入 `delete()` 协作等待轮询任务/回调结束，随后句柄失效，**即使返回硬件清理错误也不能重试旧句柄**。
- 马达 `create/delete` 必须与所有公开API互斥。`pulse/stop/get_state`平时可由不同任务调用；所有公开API禁止从ISR或esp_timer任务/回调调用。
- 马达 `delete()` 返回错误时**必须保留句柄并重试清理**；不再接受pulse，允许stop/get_state/delete。成功后旧句柄才失效。
- `state.active=false`不等于已测得物理关断；`state.faulted=true`表示输出/清理故障，不能只看active。紧急脱离LEDC后必须delete/create才能再次pulse。硬件默认关闭仍需独立核验。

完整线程/生命周期和错误语义以公共头文件为准。

### 输入基本用法

```c
#include "micro_box_s3_inputs.h"

static void on_input(micro_box_s3_input_t input,
                     micro_box_s3_input_event_t event, void *arg) {
    // Record or enqueue application work; do not block or delete this instance here.
}

micro_box_s3_inputs_handle_t inputs = NULL;
micro_box_s3_inputs_config_t cfg = MICRO_BOX_S3_INPUTS_DEFAULT_CONFIG();
cfg.callback = on_input;
ESP_ERROR_CHECK(micro_box_s3_inputs_create(&cfg, &inputs));
```

只测单触摸时设 `cfg.enable_buttons=false`；只测两按键时设 `cfg.enable_touch=false`。两项均禁用无效。触摸校准是异步的，应通过快照确认 `calibrated`，不要把create返回当作校准/实物验收完成。

### 马达基本用法

```c
#include "micro_box_s3_motor.h"

micro_box_s3_motor_handle_t motor = NULL;
ESP_ERROR_CHECK(micro_box_s3_motor_create(&motor)); // Idle, no pulse.
// Only after an explicit user/application request:
esp_err_t err = micro_box_s3_motor_pulse(motor, 200, 100, 0);
// Or 400ms total, 60% target duty, including a 40ms 100% starting segment:
// err = micro_box_s3_motor_pulse(motor, 400, 60, 40);
```

`duration_ms`为总长1～400ms，`duty_percent`为1～100%，`boost_ms`为总长内的起动段、最大40ms且不能超过总长。LEDC Timer1/Channel1、200Hz、10bit，不占相机XCLK的Timer0/Channel0。忙时拒绝，不以重复请求延长当前脉冲；停止后至少3秒冷却。占空比不是实测振动力百分比。

`stop()`可主动关闭；自动关闭由软件定时任务执行，不是硬件过流/过热/失控切断保护。退出前由所有者停止调用并按组件约束释放。

## 4. 正式例程与小智适配

| 构建目标 | 行为 |
|---|---|
| `touch` | 仅GPIO11触摸事件和raw/基线快照；马达idle |
| `buttons` | 仅GPIO12/13按下、释放、长按；马达idle |
| `motor` | USB串口V请求200ms/100%短振，X停止、S查询；无自动振动 |
| `controls` | 单触摸+双按键事件与同样的手动串口马达入口；输入事件不自动触发马达 |
| `xiaozhi` | 复用组件；网络等待之前初始化本地输入和马达idle，仅记录事件，未绑定按键业务或自动震动 |

构建统一使用 `python tools/build.py <目标>`；只生成镜像，不打开串口、不刷机。应用接入改变了原四路触摸演示动作：不再默认切眼样式/追踪/清配置，待用户明确后在应用层绑定。

原先独立实测工程 `controls-test`、`motor-test`、`motor-patterns` 作为可复现诊断保留；它们不复用本次新组件，因此其历史验收不能自动升级为新组件或小智适配的实机验收。

## 5. 测试与证据边界

已实际观察到原独立输入诊断两键按下/释放与单铜箔触摸/释放。用户曾额外按键且触摸时手未完全移开，因此只确认基本响应，不宣称精确计数和触摸重复性通过。

独立马达诊断已完成一次200ms，以及100/200/400ms时长和30/60/100%占空比对比；用户确认短振后停止，时长及弱中强区别明显，未报告持续振动、明显发热或重启。详见 [首次短振](motor-test.md)、[多组对比](motor-patterns.md)。

本次正式组件代码需要分别经过主机C行为回归、SDK实际编译和后续实机测试。源码契约检查、主机状态机测试、编译、烧录回读、现场触感、整机并发和长时间电池/温升均是不同证据层级。更新工程本身不授权重新刷机；设备当前固件以最近实机记录为准。