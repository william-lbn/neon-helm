本批为显式原UID受控Guest退役工具，不是live Root/PG的FD收养，不更改AS安全门或闭门/过期恢复例外。

新增retire action及三个可选状态字段。原部署Complete、实际ready/原Runtime Secret UID与数据摘要、原journal/CI/incarnation/标签和Controller finalizer保持；退役专用校验只允许原min/max内合法当前MemorySlots.Use（真实测试7→8），其他Spec仍原样，旧hold/render/seal的exactSpec规则不动。先将VM/同原UID CM点时库存私有内容寻址归档并fsync，再保存may-send并fsync，之后仅UID/RV正常Delete。原CM库存是点时快照，不声称收齐退出后新增全部最终来源；不保存Runtime Secret内容，不把准入Unknown说成已关闭。

may-send开始即永久拒旧state构建/封存；DELETE错误/超时、deleting或新UID均不判原Guest已停。重试只同原UID；实际404后分页核全部原UID Pod不存在+实际各Node InspectVMUnheld+再次404，才持久retired。工具不移除finalizer、不改Node账本、旧Resize未知不写NoEffect。Controller/Scheduler的真实全Pod停止/退出来源/Node结清仍是已有独立安全责任。

实际25356e Linux Go race4根10子通过，CLI build/help均0；测试先复用原Runtime公开库执行seal，再用真实typed HTTP clients验证精确DeleteOptions和先archive/may-send顺序，覆盖丢DELETE回复、坏archive、无票404、无finalizer、同名新UID、deleting、Use6/9/Max漂移、第二页Pod/Node未知等拒绝及同票恢复观察。服务端明确模拟Controller终态，不能冒真实K8s/容器/QEMU Wait或新Guest数据恢复。首次248测试编译因新增负例switch重复case失败（CLI/help0），原始失败保留；最终仅修test，生产source身份不变。4/10是稳定目标，不累计重复执行。

后续实际验收必须故障注入Root死亡→旧Guest唯一QEMU Wait/真实Pod终态与Node退休→全新state/CI/incarnation/UID原birth→从原tenant/timeline实际读取已提交数据；这不由本组件归档替代。若沿用原VM名字，等旧config Secret正常GC，不收养其旧UID。此批E0/真实Controller退役0/Source和normal false，CLI ELF仅留/data，Git只归源码和小证据。全部nonce/锁/资源/日志/终态保留并已预算reconcile，不prune。
