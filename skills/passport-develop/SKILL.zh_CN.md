---
name: passport-develop
description: 根据用户需求实现或扩展 FoloToy AI Passport 应用，组织实现、验证及真机测试交接。不用于纯咨询、仅日志诊断或发布。
---

<p align="right"><strong>简体中文</strong> · <a href="SKILL.md">English</a></p>

# 开发 AI Passport 应用

用 `git rev-parse --show-toplevel` 确定目标工作区；下列路径均相对于该工作区，
而不是安装后的技能目录。首先执行 `git status --short --branch`。
阅读 `AGENTS.md` 和 `docs/development/ai-guide.zh_CN.md`，遵循必需技能的
可用性要求，其他文档按任务加载。

## 把需求变成可工作的增量

1. 明确相关页面、按键、数据、服务及失败状态的行为和验收方式。澄清重要
   不确定项，说明合理默认值。不得猜测硬件事实，或擅自添加联网、云服务、
   接线及付费依赖。
2. 沿用目标应用和分支，保留现有修改。新应用使用约定基线及适用的分支规范。
   修改冲突或目标不明确时与用户解决。
3. 查看相关示例分支与 `docs/reference/README.zh_CN.md`，提取可复用模式。
   二次开发应用须按 AI 指南的强制重新设计规则实现自己的 UI；可复用 BSP API
   和独立逻辑。
4. 实现最小完整行为，为纯逻辑添加主机测试，遵循 AI 指南中的应用／BSP
   边界和运行时约束。
5. 修改中运行针对性检查，交付前运行完整 `./tools/validate.sh` 门禁。修复
   本次修改引入的失败；无关或环境阻碍应附证据和可执行下一步。

## 按需使用专项流程

| 场景 | 技能 |
| --- | --- |
| 工具链缺失或异常 | `passport-setup` |
| 验证与打包固件 | `passport-build` |
| 用户同意真机测试 | `passport-device-test` |
| 运行故障或崩溃 | `passport-debug` |

## 交接与继续开发

报告已实现行为、下一步，并分别报告 `Build`、`Host tests`、`Device tests`
和 `Unverified`。涉及二次开发应用 UI 时，说明页面和按键交互，检查启动与
导航使用应用自己的 UI。跨会话工作仅按需更新已有项目记录。

每轮完整实现固件需求后，按 AI 指南的真机交接流程主动邀请测试。烧录需要
明确授权，编译完成或 USB 已连接不代表同意。未经授权不得提交、推送或发布。
