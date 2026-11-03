# 原 held VM 到三份 Runtime 输入

`render` 是现有首次部署工具的窄步骤，不启动控制面服务，不创建签名体系或预算资格。只读实际 API，保留原 incarnation/Compute实例/issuer epoch/预算ID/公钥与额度，仅将两个原模板的空 VMUID 绑定为 `hold` 已持久确认的真实 VM UID。

执行顺序为 `hold → render → seal → inspect`。`render` 不创建 Secret、不投影临时 SecretUID、不释放VM。完整 Runtime/policy 语义仍在 `seal` 获取真实 API SecretUID 后，调用原 `bootstrap.Runtime` / `RenderRuntimePolicyAssets` / `DeriveRuntimeBootRequirements`，最后原 UID/RV CAS 释放。

必需输入均来自原可信部署计划与准确发行构建：

- 原私有 Compute config 模板：只允许 `spec.dynamic_shared_buffers.vm_uid` 为空；协议2、Compute实例、最低7GiB与bootstrap字节明确，原 storage/认证/业务字段原样保留。
- 原私有 SourceConfig 模板：Config.VMUID为空，execution_model明确trusted-controller-v1，原 Limits/固定StateDir/System/issuer1/预算ID/管理公钥完整。这里复用旧纯renderer的SourceConfig合同，不调用旧CP服务。
- 原完整policy template字节与原 Builder NativeBirth manifest。不得从模型 Runtime 提取已绑定 UID/资格或测试0x39 key作为正式来源。
- 原发行构建索引：protocol_version=1、scope=neon-pg17-trusted-runtime-build-v1；guest_image/runner_image/kernel_image 必须等于原held VM的准确digest，policy_templates_sha256/native_build_sha256覆盖上述原字节，compute_config_path等于原镜像构建计划固定的/neonvm/config/compute-public.json（只含公开JWKS，spec为空）；VM不注入env/挂载盘/命令。封存后通过现有management Gateway的configure API交付原Secret中的业务spec。索引是构建输入记录，不是内存预算/Source许可。

工具不填默认P/A/N/Outside，不从RSS或Linux模型预算生成新上界；PCP1024/P256/System512及初始额度来自原已审policy与实际镜像。原公开Source.Validate/TotalUpperBytes先核结构、身份、公钥、完整额度可表示且适合原最低Guest。Compute和Source的唯一Ed25519验证公钥必须相同，不读取或输出签名seed。render与手工seal共用strict public-only JWK校验，只接受原六个公开字段与可选kid，d/未知成员在任何Secret API前拒绝。

Compute/Source模板必须为原私有regular文件（0600），公开构建文件不能被group/other写。不跟随最终symlink，读取前后核同文件/大小/mtime。输出父目录必须已存在且0700；只在新的私有目录以0600+fsync形成完整三文件，再NOREPLACE原子发布。同一原输入可读取确认，漂移输入不能覆盖已发布文件。同字节恢复仍重新fsync原三文件、输出目录及父目录，不能把前次rename后未确认耐久的Unknown直接当成功。

```sh
# 先按 README.zh-CN.md 的 source-lock 步骤取得隔离 AS73c1 源码并核SHA。
# 必须从该 AS 模块根编译全4个生产文件；工具目录没有独立go.mod。
cd "$TASK_AS_SOURCE"
GOWORK=off CGO_ENABLED=0 go build -mod=readonly -p=2 -ldflags="-s -w" \
  -o /data/neon-build/bin/neon-runtime-prepare \
  "$TASK_TOOL_SOURCE/main.go" "$TASK_TOOL_SOURCE/render.go" \
  "$TASK_TOOL_SOURCE/recovery.go" "$TASK_TOOL_SOURCE/service.go"

neon-runtime-prepare -action render -kubeconfig <既有配置> -vm-json <原held-vm.json> -state /data/<本次归档>/deployment/state.json -compute-config <原私有unbound-compute.json> -resource-config <原私有unbound-resource.json> -policy-templates <原完整policy-templates.json> -native-build-manifest <原Builder-native-build.json> -build-contract <原发行build-index.json> -render-output-dir /data/<本次归档>/deployment/rendered

# 后继seal只消费该目录的原三文件：config.json、resource.json、dsga-policy-templates.json。
```

没有实际发行索引/可信key或Source时必须保持held，不能复制单机模型UID/0x39key/资格或用测试seed填补。现验证仅为typed fake API单元与工具编译，不是Kubernetes/单服务/E通过。
