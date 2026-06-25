# Super Search Skill

一个给 Codex 用的“搜索路由器”Skill。

它不是新的搜索引擎，也不是要把所有接口都包一遍。

它做的事情更小，也更关键：

> 先判断应该去哪搜，再决定要不要真的调用搜索、付费源或浏览器。

## 为什么做这个

很多时候，我们对 AI 说“搜一下”，其实不是一个动作。

它可能是：

- 读一个网页链接
- 找 GitHub 上的类似项目
- 查普通网页资料
- 看公众号、抖音、小红书里的中文内容
- 查 TikTok、Instagram、X、Reddit 这类社媒数据
- 打开浏览器，登录后台，截图或下载文件

如果没有路由，AI 很容易直接凭感觉行动。

这会带来几个问题：

- 明明应该查 GitHub，却只搜了网页。
- 明明免费源够用，却先调用付费 API。
- 明明只是要读资料，却开始动浏览器和账号状态。

Super Search 的原则是：

> 免费、只读、低风险的动作可以自动跑。
> 付费、登录、点击、下载这类动作必须先确认。

## 它能做什么

当前版本是一个 MVP，已经支持这些路由：

| 查询类型 | 默认路由 | 说明 |
| --- | --- | --- |
| URL / 链接 / 文章 | Jina Reader | 读取网页正文，避免一上来开浏览器 |
| GitHub / 开源项目 / 仓库 | GitHub CLI + Exa | 先查仓库，再补充网页语境 |
| 普通网页调研 | Exa | 走语义网页搜索 |
| 公众号 / 抖音 / 小红书 / 视频号 | RedFox 提示 | 当前只提示，不自动调用付费源 |
| TikTok / Instagram / X / Reddit / YouTube | TikHub 提示 | 当前只提示，不自动调用付费源 |
| 登录 / 点击 / 截图 / 下载 / 后台 | 浏览器兜底提示 | 当前只提示，需要确认后再执行 |

## 仓库内容

```text
.
├── SKILL.md                 # Codex Skill 入口
├── scripts/
│   └── super_search.py      # 可直接运行的搜索路由脚本
├── config/
│   └── mcporter.json        # Exa MCP 配置示例
└── agents/
    └── openai.yaml          # Agent / OpenAI 侧描述
```

## 安装到 Codex

把仓库克隆到本机 Codex skills 目录即可。

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/duevan07/super-search-skill.git ~/.codex/skills/super-search
```

然后重启 Codex，让新 Skill 被加载。

如果你已经装过，更新即可：

```bash
cd ~/.codex/skills/super-search
git pull
```

## 依赖

最小依赖：

- Python 3
- `curl`

按路由启用的可选依赖：

- GitHub 搜索：需要安装并登录 GitHub CLI，也就是 `gh`
- 网页搜索：需要本机可用的 `mcporter` 和 Exa MCP 配置
- URL 阅读：走 `https://r.jina.ai/`，需要能访问外网

没有某个依赖时，脚本不会假装成功。

它会把失败原因写进 `notes`，方便你选择下一个更小的 fallback。

## 快速开始

先看路由，不真正调用外部搜索：

```bash
python3 scripts/super_search.py "github 上类似 Agent Reach 的项目" --dry-run --format json
```

读一个链接：

```bash
python3 scripts/super_search.py "https://example.com"
```

找 GitHub 项目：

```bash
python3 scripts/super_search.py "firecrawl alternatives github" --mode github --limit 5
```

输出 JSON，方便后续做表格、报告或二次分析：

```bash
python3 scripts/super_search.py "Agent Reach 类似项目" --mode github --limit 5 --format json
```

如果你把脚本放进了 PATH，也可以直接用：

```bash
super-search "Agent Reach 类似项目" --mode github --limit 5
```

## 在 Codex 里怎么触发

安装后，新对话里遇到这些表达，Codex 会优先使用这个 Skill 做路由：

- 搜一下
- 查一下
- 调研一下
- GitHub 上找找
- 读一下这个链接
- 看看有没有类似项目
- 这个应该去哪搜

它的目标不是替你做所有决定，而是先把搜索动作分清楚。

## 设计边界

这个项目刻意不做几件事：

- 不自动调用 RedFox、TikHub、AgentKey 等付费或账号相关能力。
- 不自动登录网站、点击按钮、提交表单或下载私有数据。
- 不自己发明不存在的接口。
- 不在 provider 失败时假装已经查到。

如果结果不够，下一步可以再扩展到 Agent Reach、RedFox、TikHub 或浏览器自动化。

但扩展应该有判断条件，有确认步骤，有测试结果。

## 验证

在仓库根目录运行：

```bash
python3 scripts/super_search.py "https://example.com" --dry-run --format json
python3 scripts/super_search.py "github 上类似 Agent Reach 的项目" --dry-run --format json
```

你应该能看到类似这样的路由信息：

```json
{
  "plan": {
    "providers": ["github", "exa"]
  },
  "notes": [],
  "results": []
}
```

`--dry-run` 只验证路由，不会真的调用搜索源。

## 后续可扩展方向

- 结果质量评分
- “结果不够”时自动降级到 Agent Reach
- RedFox adapter
- TikHub adapter
- AgentKey adapter
- 浏览器兜底确认流程
- 缓存、预算上限和调用审计

## 核心原则

这套 Skill 的核心不是“能搜更多地方”。

而是让 AI 在搜索前先停一下：

> 这个问题，应该去哪搜？

先路由，后搜索。
