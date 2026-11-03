修复实际建桶Job把无shell的静态mc当/bin/sh运行的问题：直接mc mb，Secret引用经Kubernetes前序env展开到MC_HOST_local，不把凭据写进参数/values/源码。
原mc镜像同根因目录mode错误另用最薄层修/etc三目录为0755，ELF/CA/非root/入口均不变，新pin见receipt。未改宿主DNS/网络，旧镜像与原失败票保留。
实际neon-pg17-core rev4已deployed：MinIO/PS/3SK/broker 6Ready0restart，5PVC Bound，真实认证建桶hook2次成功；仅数据基础链，VM自动扩缩端到端尚未验收。
复现：python3 docs/validation/minio-shellless-job-20261103/check-minio-shellless.py charts/neon-core docs/validation/minio-shellless-job-20261103/values.fixture.json
