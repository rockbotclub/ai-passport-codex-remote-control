<p align="right">
  <strong>简体中文</strong> · <a href="README.md">English</a>
</p>

# 资源目录（Assets）

本目录集中存放可复用的资源（字库、图片、音乐等），按资源类型分子目录管理。每个资源放在其类型对应的子目录，并记录放置路径、命名方式、集成方式与来源/许可。二进制资源（字体、图片、音频）不属于纯 markdown 文档，请勿与文档混放。涉及版权/授权的资源需注明来源与许可。

## 字库（fonts）

可复用的字库文件与生成的字库源码放在 `fonts/`。

- 命名要能反映字族、字重、字级与格式。
- 记录来源、许可、字符范围、转换命令与目标放置路径。
- 添加字库前评估 Flash 与内部 RAM 影响；ESP32-C3 无 PSRAM。
- 不提交许可不允许分发的字库。

Codex 宠物使用 `fonts/PassportSans-Regular.otf`，它是
[Noto Sans CJK SC Regular](https://github.com/notofonts/noto-cjk/tree/main/Sans/OTF/SimplifiedChinese)
的重命名字体子集，采用 [SIL OFL 1.1](fonts/OFL-NotoSansCJK.txt) 许可。原始下载 OTF 的
SHA-256 为 `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`。
子集保留上游版权元数据，并重命名为 Passport Sans。
`fonts/passport-ui-glyphs.txt` 记录可打印 ASCII 和固件固定中文字库，使用 FontTools
4.66.1 提取子集。生成的 `fonts/passport_font_12.c`、`passport_font_14.c` 和
`passport_font_20.c` 兼容 LVGL 9.5，采用 2-bpp、无压缩格式存于 Flash，由 `main`
编译，并由 `main/pet_ui.c` 中所有本地文字控件显式选用。
每种字号包含 265 个字形。已验证的 MAP 记录字体只读数据合计 42,072 字节
（分别为 9,537／11,866／20,669 字节），这些字体对象不占用 `.data` 或 `.bss`。

使用 `lv_font_conv` 1.5.3 重新生成各字号（其他字号将两处 12 同时替换为 14 或 20）：

```bash
npx --yes lv_font_conv@1.5.3 --font assets/fonts/PassportSans-Regular.otf \
  --symbols "$(cat assets/fonts/passport-ui-glyphs.txt)" --size 12 --bpp 2 \
  --format lvgl --no-compress --no-kerning --lv-include lvgl.h \
  --lv-font-name passport_font_12 \
  -o assets/fonts/passport_font_12.c
```

新增字符时先扩充清单，必要时从上游字体重新提取 OTF 子集，再生成全部字号。
该子集只供本地固定文字使用，任意项目名及审批内容由电脑绘制。
`tools/codex_pet/ui_glyphs.py` 单独记录电脑端固定提示字形清单，本地化测试会将其与
Python 源码核对；修改提示后使用 `python3 tools/codex_pet/update_ui_glyphs.py` 更新。
字体无需扩大 LVGL 堆；运行时剩余堆内存及最大连续内存块仍需设备实测。

## 图片（images）

可复用的源图与生成的显示资产放在 `images/`。

| 文件 | 尺寸与格式 | 用途与来源 |
| --- | --- | --- |
| [`images/home.jpg`](images/home.jpg) | 3840 × 2160，JPEG | 嵌入中英文项目 README 的产品主图，突出 AI Passport 产品形象与开放、人人可创作的理念。 |
| [`images/readme-hardware-specs.png`](images/readme-hardware-specs.png) | 2172 × 724，PNG RGBA | 保留为可选技术参考图，不再用于首页主视觉。于 2026-09-17 使用内置图像生成工具为本仓库生成；已根据文档中的硬件能力契约核对图中的六项标签与参数。 |
| [`images/logo-wordmark.png`](images/logo-wordmark.png) | 1648 × 336，PNG RGBA | 从仓库原始 `images/logo.png` 中精确裁切并去除背景的黑色字标；用于中英文项目 README 的浅色主题。 |
| [`images/logo-wordmark-dark.png`](images/logo-wordmark-dark.png) | 1648 × 336，PNG RGBA | 提取字标的白色版本；README 使用 `<picture>` 在 GitHub 深色主题下显示。 |

- 使用描述性命名，并记录尺寸、像素格式、转换步骤与目标路径。
- 优先采用适合 240 × 320 RGB565 显示的格式，并纳入 Flash 与内部 RAM 考量。
- 许可允许时保留可编辑源文件，并记录来源与许可。
- 图片中不得包含设备二维码秘密、凭证或个人数据。

## 音乐与音效（music）

可复用的音乐与音效源码放在 `music/`。

- 记录来源、许可、采样率、位深、声道、转换命令与目标路径。
- 与当前 BSP 音频路径匹配时优先采用 16 kHz、16 位单声道 PCM。
- 嵌入音频前评估 Flash 与内部 RAM 成本；长录音应流式或分块。
- 无再分发许可不提交媒体文件。

## 本地 Codex 宠物素材

`images/codex-pet/source.webp` 和 `frames.inc` 由 `tools/codex_pet/prepare_sprites.py` 从用户的 Codex 安装中导入。31 帧 RGB565 图像为 144 × 156 像素，直接嵌入 Flash。文件被 Git 忽略，尚未确认再分发授权。参见[应用指南](../docs/codex-pet.zh_CN.md)。

同一导入工具生成 `images/codex-pet/offline.inc`：216 × 144 的单色位图，
以 16/12 像素显示“电脑连接已断开”和“请检查电脑端连接程序”，使用本地 Arial
Unicode 或通过 `--font` 明确指定的字体。生成前检查字符覆盖，占用 3,888 字节
Flash，复用现有界面列表缓冲区。这份由字体生成的资源也被 Git 忽略；字体与
宠物素材的再分发授权尚未确认。

导入器还会生成 `images/codex-pet/syncing.inc`，包含“正在同步任务”和
“正在读取电脑任务状态”。使用相同的已验证字体、16/12 像素字号、216 × 144 位图
及现有列表缓冲区，增加 3,888 字节 Flash，使首个加密总览到达前也能显示同步提示。
这份资源同样被 Git 忽略，适用相同的再分发限制。
