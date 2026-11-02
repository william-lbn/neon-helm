PG17 K8s 内存管理TLS与真实UID管理Service接线（2026-11-02）

本批只补PG17内存扩缩容E所需部署入口，不代表控制面产品完成、真实K8s通过或Source/normal合格。
专用管理HTTPS由原gateway独立8444终止TLS；Agent沿原TokenReview/短令牌/JWK链，不复制Linux固定测试key。现有公共8443与禁用DSGA的旧路径保留。

重要修正：proxy现有代码只核专用Service路由/labels/UID/RV；没有Service ownerReferences gate。原creator有真实VM UID owner/创建注释/GC合同，本批保持它。Helm只渲染held VM与身份输入，不再预造无真实UID的management Service。
新runtime-prepare在实际held VM UID后、ReleaseBootstrap前先持久management Service may-have-sent，再单次CREATE，记实际Service UID/RV并GET严格核验，最后封存完成前再GET。已有同名但无原收据、未知CREATE、删除/替换UID、owner/labels/注释/selector/额外端口等漂移均拒，不PATCH/补签/自动重建。原retire删除/Node结清流程不改；其模型HTTP夹具仅补Service GET。

实际验证：993ee1的13个race根/50子项、CLI/help均0；BuildKit已完成，原外层collector因新source-lock未带旧expected_tests字段KeyError退出1。该wrapper失败原件保留，actual-phase-result.json仅记录原测试/产物真实收据，未重标wrapper成功、未重复构建。
Helm51f6c6：3个正向、6个反向、2个lint及5个结构断言通过。只移除早期无UID Service，其余Compute与gateway资源逐结构等旧已验证输出。前置两次driver失误（缺原runtime allowlist键、缺--kube-version1.31.2）原目录保留，不计通过。

本工具构建必须包含四个生产文件；测试必须包含四个对应测试文件：
go build -o neon-runtime-prepare tools/runtime-prepare/main.go tools/runtime-prepare/render.go tools/runtime-prepare/recovery.go tools/runtime-prepare/service.go
go test -race -count=1 tools/runtime-prepare/main.go tools/runtime-prepare/render.go tools/runtime-prepare/recovery.go tools/runtime-prepare/service.go tools/runtime-prepare/main_test.go tools/runtime-prepare/render_test.go tools/runtime-prepare/recovery_test.go tools/runtime-prepare/service_test.go
依赖由准确AS公共库提供，测试使用Kubernetes API模型，生产命令使用真实typed API；不得把模型UID当部署输入。私有CA/叶key/32-byte seed只留/data私有文件和真实Secret，未提交。

工作负载仍需单机门槛后由Root核实际目标；仅117/118/119，排除116。此档 Secrets_created=false/workload_deployed=false/K8s=false/E=0。

独审补丁：projectId作为Kubernetes label，仅允许原ASCII字母/数字/下划线/连字符，长度1..63且首尾必须字母或数字；未新增点号。guard与schema同步，实际short/63字符正控、64字符与两种尾符号负控及63字符lint通过。原8aeb9ad3提案保存为历史，新的r2提案为准；Service13race50sub未重复跑。
