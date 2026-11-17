# 视频壁纸素材研究

一个查找可下载视频壁纸的通用 Agent Skill。按作品、角色、作者或截图追溯素材，从公开投稿找到网盘入口，核实真实文件、分辨率、日期和下载条件。

支持 B 站、夸克的具体查找与目录核验方法；其他平台沿用相同证据标准。筛选条件从当前任务继承，不强制所有任务都使用夸克或只收录 4K。

## 使用

安装后可直接向支持 SKILL.md 的 Agent 提出：

> 使用 $video-wallpaper-research 找最近更新的陆雪琪 4K 动态壁纸，只要夸克，排除已经找到的同场景素材。

也可以要求：

> 根据这个分享截图追溯发布者，查找其公开合集；没有总包就整理已核实的分享索引。

技能会区分预览线索、云端目录核实、原片下载、本地解码和应用实测，不把较低阶段包装成更高阶段。搜索任务不自动修改壁纸或发布新分享。

## 安装

使用 [Skills CLI](https://github.com/vercel-labs/skills) 安装，需要 Node.js 22.20+ 和 Git：

~~~bash
npx skills add Lumiaqian/video-wallpaper-research
~~~

按提示选择 Agent；默认安装到当前项目。若要全局安装供 Codex 使用：

~~~bash
npx skills add Lumiaqian/video-wallpaper-research -g -a codex -y
~~~

安装器负责目录和来源记录。当前 CLI 的 Codex 全局安装位置为 `~/.agents/skills/video-wallpaper-research`，无需手动克隆仓库或建立两套目录链接。其他 Agent 按安装器的选项选择。

如果以前手动链接到了开发仓库，迁移前先保留本地修改，并移除指向开发仓库的旧链接，再运行安装命令。

需要固定版本时，可使用标签 URL：

~~~bash
npx skills add https://github.com/Lumiaqian/video-wallpaper-research/tree/v0.1.0 -g -a codex -y
~~~

也可以从 [GitHub Release](https://github.com/Lumiaqian/video-wallpaper-research/releases) 下载 ZIP，将解压后含 SKILL.md 的目录放入目标 Agent 的技能目录；手动安装的副本由自己更新。

## 更新

通过安装器跟踪主分支安装的全局副本，可以单独更新这个技能：

~~~bash
npx skills update video-wallpaper-research -g -y
~~~

固定标签安装的副本需要重新运行 `skills add`，指定新的标签。回退时指定之前的标签。

查看 Codex 的全局安装：

~~~bash
npx skills list -g -a codex
~~~

项目级安装省略 `-g`，并在对应项目中执行。

## 目录核验脚本

使用 Python 3.9+，仅依赖标准库；浏览器和登录操作由当前 Agent 环境提供。脚本不需要账号 Cookie，只读取公开分享目录，不下载或转存原片。

在安装后的技能目录中运行：

~~~bash
python3 scripts/inspect_quark_share.py 'https://pan.quark.cn/s/SHARE_ID' --output /absolute/path/share-evidence.json
~~~

默认只扫描 300 个条目、子目录深度 2，并按云端至少 3840×2160 筛选 MP4/MOV/M4V。可以调整扫描范围和尺寸门槛；达到扫描上限会明确标为不完整。

`eligible_media` 只是云端元数据达标，不能据此宣称实际下载成功、原生 4K 或循环正常。提取码、定向扫描与字段说明见 [平台参考](references/bilibili-quark.md)。

## 开发与发布

- [SKILL.md](SKILL.md)：使用场景、查找策略和证据边界。
- [平台参考](references/bilibili-quark.md)：B 站、夸克的具体方法。
- [记录格式](references/evidence-format.md)：日期、来源、去重和核验阶段。
- [CHANGELOG.md](CHANGELOG.md)：每个版本的用户可见变化。
- [VERSION](VERSION)：当前源码版本。

开发时单独克隆本仓库，修改源码后通过安装命令更新使用副本。main 保存可用版本，改动通过功能分支审阅后合并。发布时更新 VERSION 和 CHANGELOG，完成相关验证后创建版本标签及 GitHub Release；保留已发布标签的内容。ZIP 使用标签归档，不混入个人下载、检索输出和账号数据。

## 验证与打包

~~~bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py' -v
git diff --check
~~~

测试覆盖尺寸与格式筛选、分页、扫描范围、不完整目录和安全错误输出。接口可能变化，发布前应另外选少量公开分享做只读核验；不能因接口读取成功推断账号可下载。

在已创建并核实版本标签后，从相同标签生成发布包：

~~~bash
mkdir -p dist
git archive --format=zip --prefix=video-wallpaper-research/ --output=dist/video-wallpaper-research-v0.1.0.zip refs/tags/v0.1.0
~~~

每个 Release 附该 ZIP 和对应版本的变更说明。版本化管理范围是技能说明与辅助脚本；素材版权、网盘权限和服务状态仍取决于原来源。

## 许可

[MIT](LICENSE)。不包含视频素材，许可不授予第三方素材的使用权。
