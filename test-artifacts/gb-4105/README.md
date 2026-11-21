# 日加权剖面 · 测试与验证（gb-4105）

## 运行方式
```sh
python3 -I test_profile_engine.py    # 引擎口径（31项）
python3 -I test_profile_service.py   # 服务层集成：真实profiles.py + fakedeps（19项）
python3 -I test_seed.py              # 种子幂等与样例（6项）
node --experimental-default-type=module test_frontend.mjs  # 前端页面渲染（11项）
```

## 覆盖要点
- 同刻读数先取均值；后一采样封段，末采样不计；超一小时整段不计，恰好3600秒计入。
- 跨午夜按时长分摊；America/New_York 春季23小时/秋季25小时实际日长；Asia/Shanghai当地日归属。
- 查一天也取窗外能封段的采样（窗口前一后一）。
- 受理版快照计算；计划行保留前缀（filter生效、hash_join重复右键被同刻均值中和、group拒绝）。
- 中间记录500条一批（601采样→2批），结果与不分批一致。
- 断点恢复：模拟worker进程被杀（KeyboardInterrupt），保持running、从断点续跑、重试不重复累计、恢复结果与一气呵成同checksum。
- 每天核齐才出结果（不变量：覆盖非负且不超实际日长、均值落在当日段值域、全部设备有日记录）。
- 可恢复错误：坏recorded_at、无效时区、超62天、未知计划、含group计划。
- 种子幂等；前端表单/列表/明细/执行中/空状态渲染。

fakedeps/ 仅为本仓库用到的 sqlalchemy/redis/fastapi/jwt 最小子集，用于在无三方依赖的环境里驱动真实服务代码；读时复制、commit合并，模拟事务回滚。
