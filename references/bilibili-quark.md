# B 站与夸克：从投稿追溯到视频文件

这些是公开页面和接口的实测方法，不是稳定 SDK 契约。字段、登录要求和页面随时可能变化；使用时先小样本复核。请求失败就换公开网页核验，不猜下载接口、不反复重试。

## B 站发现与作者追溯

- 使用当前搜索语言规则，保留中文专名。例如 `"陆雪琪" "动态壁纸" 4K Quark download`。平台内可按原文作品名定位；按“最新发布”排序比搜索引擎抓取时间可靠。
- 投稿页先读取标题、UP 主、发布日期、简介，再看作者发布的评论及置顶。普通观众的链接只能标为第三方分享。
- 自动连播可能很快跳到下一条推荐。核实当前 BV 号、页面标题和作者，必要时用界面播放／暂停按钮停下。
- 单页刚导航时可能暂时显示空白／“什么都没有”，待页面完成加载再判断。不要因骨架页误报无资源。
- 控件输入如果发生追加，用全选、清空后重新输入；搜索词改变后确认排序仍是“最新发布”。
- 只操作用户授权的公开页面；不私信、加群、关注或索取私人网盘内容。

有公开网络读取能力时，可以按 BV 号读取：

~~~text
GET https://api.bilibili.com/x/web-interface/view?bvid=BV...
User-Agent: Mozilla/5.0
Referer: https://www.bilibili.com/
~~~

常见字段位于 data：
- aid、bvid、title、desc、owner.mid、owner.name、pubdate。
- ugc_season.id、title、sections[].episodes[] 提供合集入口和条目。每条投稿的实际简介需单独读取，不能把合集条目的空 arc.desc 误当完整简介。
- pubdate 是 Unix 秒。需要中国发布时间时转为 UTC+08:00；页面可能按本地浏览器时区显示。
- B 站合集地址形如 `https://space.bilibili.com/UID/lists/SEASON_ID?type=season`，它是视频合集，不等于网盘总包。

公开评论入口：

~~~text
GET https://api.bilibili.com/x/v2/reply?pn=1&type=1&oid=AID&sort=1
~~~

检查 data.replies、hots、top_replies，以及 top 内实际出现的评论结构；包含链接的评论需对比 member.mid 与投稿 owner.mid。只读到首页评论就只声称首页核查范围，不称“所有评论没有链接”。

昵称截断、遮蔽与头像相似都不足以认定两个账号是同一人。能够确认的是“这条投稿／作者评论提供了这条分享链接”。

## 夸克公开目录

官方分享页面形如 `https://pan.quark.cn/s/SHARE_ID`。标题“某某的分享”不是可枚举该账号全部分享的主页入口。截图没有 URL 时，先从当前页面或公开投稿取得精确分享地址。

优先运行技能自带脚本。它仅依赖 Python 标准库：

~~~bash
python3 SKILL_DIR/scripts/inspect_quark_share.py 'https://pan.quark.cn/s/SHARE_ID' --output /absolute/path/share-evidence.json
python3 SKILL_DIR/scripts/inspect_quark_share.py 'https://pan.quark.cn/s/SHARE_ID' --folder-id PUBLIC_FOLDER_ID --max-depth 1 --max-entries 100 --output /absolute/path/folder-evidence.json
~~~

- 默认最多扫描 300 个条目、子目录深度 2；列表分页每次最多 100 个。优先定位角色／月度目录后定向核实，不递归拉取整个大网盘。
- 输出中目录的 folder_id 可用于第二条命令。以该目录作为新起点后，relative_path 也从新起点计算。
- 达到条目或深度限制、目录读取失败或分页提前返回空页时，`listing_complete=false`。用 `unvisited_folders` 和 `errors` 说明缺口，此时“未找到”只适用于已读范围。
- 默认 eligible_media 只包含扩展名为 MP4/MOV/M4V、云端像素至少 3840×2160 的文件。若要求其他口径可调整 --min-width／--min-height。文件扩展名并不证明内部容器与编码。
- eligible_media 仍只是“目录及云端元数据达标”，download_status=not_attempted，不保证本账号可下载。
- 分享有提取码时，设置临时环境变量 QUARK_SHARE_PASSCODE，再加 --passcode-env QUARK_SHARE_PASSCODE；不将码或访问令牌写入输出。
- 脚本不接受 Cookie／登录态。请求失败时只输出类型或状态码，不保存带 stoken 的临时 URL。
- HTTPError、登录要求、功能受限、限流都应保留原状态，不直接判为链接过期。

接口实现集中在脚本中。当前路径：
- POST `https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc`，请求体为 pwd_id、passcode，获得临时公开分享 stoken；不代表登录账号。
- GET `https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail`，传入 pwd_id、stoken、pdir_fid、_page、_size 等，读取实际 data.list。
- 媒体相关字段可能包括 file_name、dir、size、video_width、video_height、duration、fps、created_at、updated_at；缺失就输出 null。云端文件日期一般为 Unix 毫秒，脚本转换为明确的 UTC 时间。
- 私密令牌只在单次请求内存中使用；不要在工具输出里打印整段原始响应或构造好的请求 URL。

## 原片下载和壁纸核验

需要登录的正常下载走用户指定的网页或官方客户端，不猜测未验证的下载接口。只查链接的任务不批量下载原片。

请求下载时核对目标文件名、尺寸、字节大小和保存位置；下载完成后用现有工具读取真实媒体信息。例如已安装 ffprobe 时：

~~~bash
ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,avg_frame_rate:stream_tags=rotate:stream_side_data=rotation -show_entries format=duration,size -of json /absolute/path/video.mp4
~~~

需要实证动态和循环时再解码不同时间画面、观察接缝；不用 B 站压缩预览或网盘缩略图代替原片。macOS 没有 ffprobe 时可使用系统 AVFoundation 或已有应用，不为本流程强行安装解码工具。

看见网盘里有文件与真正下载成功是不同证据。账号被限制时不要擅自判断是分享者账号还是当前账号的问题；按界面实际提示描述，保留可用公开入口。
