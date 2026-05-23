
# 南方科技大学计算机网络课程作业 — 说明文档

> 说明：本仓库包含两份实验/作业实现（Assignment_1 与 Assignment_2），仅作学习参考，请勿用于商业用途或直接抄袭提交。

## 项目概览
- Assignment_1：基于简化的 Tracker + Seeder + Requester 的点对点文件共享示例，使用 Flask 提供 HTTP 文件下载与 Tracker 注册/查询功能。
- Assignment_2：基于 UDP 的分段可靠传输与距离向量路由模拟（带丢包、差错与重传机制），通过命令行交互控制发送与路由查看。

## 文件结构

- Assignment_1/
	- `example.txt`：示例共享文件（莎士比亚合集节选）。
	- `seeder.py`：seeder 节点；会将共享文件复制到 `peer_6881`，生成 `.torrent`（使用 bencode 编码），向 Tracker 报告并启动 HTTP 服务以响应 `/download` 请求。
	- `requester.py`：requester 节点；从 `peer_6882` 目录读取 `example.torrent`，向 Tracker 获取种子列表并从 seeder 下载文件。
	- `Tracker.py`：Tracker 服务，提供 `/announce`（注册）与 `/get_peers`（查询）接口。

- Assignment_2/
	- `config.json`：节点配置（节点 ID → [IP, port]）和链路代价（distance/vector links）。
	- `input.txt`：用于模拟分段传输的测试大文件内容。
	- `peer.py`：主程序，运行后会监听 UDP、维护距离向量并支持命令行指令（例如 `send <目标ID> <文件名>`、`routes`、`check`）。

## 依赖（建议使用 Python 3.8+）
- 请求/网络与服务：`flask`, `requests`, `bencodepy`（Assignment_1）
- 标准库：`socket`, `threading`, `json`, `hashlib`, `zlib` 等（Assignment_2 使用标准库）

可用安装命令：

```bash
python -m pip install --user flask requests bencodepy
```

（在虚拟环境中安装更好：`python -m venv .venv && .venv\Scripts\activate && pip install flask requests bencodepy`）

## 运行说明

Assignment_1（Tracker + Seeder + Requester）：

1. 启动 Tracker：在 `Assignment_1` 目录下运行

```bash
python Tracker.py
```

2. 启动 Seeder（生成 torrent 并向 Tracker 登记，然后在 `peer_6881` 上提供下载服务）：

```bash
python seeder.py
```

Seeder 会将 `example.txt` 复制到 `peer_6881`，生成 `example.torrent` 并把副本放到 `peer_6882`（以便 requester 使用）。

3. 启动 Requester：

```bash
python requester.py
```

Requester 会从 `peer_6882/example.torrent` 读取 info_hash，向 Tracker 查询种子并尝试通过 HTTP 从 seeder（`/download`）拉取文件。

注意：上述示例默认使用本地回环地址与端口（Tracker:5001，Seeder:6881，Requester:6882）。如果在不同主机或不同端口运行，请相应修改文件内的 `TRACKER_URL` 与端口常量或 `peer_*` 目录结构。

Assignment_2（UDP 分段可靠传输与距离向量路由）：

1. 在 `Assignment_2` 目录下，确保 `config.json` 配置了你要模拟的节点（默认示例中有 Peer1..Peer5）。

2. 启动某个节点（在不同窗户/终端分别启动多个节点以模拟网络）：

```bash
python peer.py --id Peer1
python peer.py --id Peer2
```

3. 在节点提示符下使用命令：

- `send <目标ID> <文件名>`：将当前目录下的 `<文件名>` 按段发送到目标节点（目标不应等于自己）。
- `routes`：打印当前节点的路由表（距离向量）。
- `check`：查看接收缓冲区中已收到与缺失的段。

接收的文件将被组装并保存为 `files/<PeerID>/received_file.txt`。

提示：`config.json` 中演示使用了不同的 IP（127.0.0.1..127.0.0.5）；在本地单机测试时，你可以把所有节点的 IP 都改为 `127.0.0.1`，并确保使用不同端口，以便在同一台机器上运行多个实例进行仿真。

## 已知注意事项与调试建议
- 若要在单机上同时运行多个 Assignment_2 节点，请为每个节点分配不同端口并在 `config.json` 中对应修改 IP/port。
- 如果防火墙或端口被占用，UDP 监听会失败，请检查端口与防火墙设置。
- Assignment_1 使用 `bencodepy` 来生成/解析 torrent，确保安装该包。

## 许可与声明
- 本仓库为课程作业代码示例，仅供参考、学习与实验用途。请按照课程要求完成自己的实现并注明引用。

如果你希望我为你：
- 运行一次示例并记录终端输出，或
- 将 `config.json` 修改为单机多端口可运行的版本，
请回复我想要的操作。谢谢！
