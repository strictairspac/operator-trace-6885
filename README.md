# 松原 · 分析算子执行剖面仪

松原数据库教学研发组 6 人用真实 Python scan/filter/hash join/group 算子，复查一条分析查询的每一步输出。

## 场景与模块
上游是设备可靠性课程的采样文件、传感器表和分析需求。过去在白板画算子、手动算中间行数，再把截图发给助教；重复键丢失、空结果误判、输入版本变化后无法复现实验是三个痛点。本站保存数据集与有界计划 DSL，worker 真执行并保存不可变快照/逐步摘要，下游讲师和同学只读复查。

数据集录入/编辑、算子计划编排、执行队列、算子剖面/JSON导出、日加权剖面五个业务页面；管理员有审计。四个实体 datasets / plans / traces / profiles 均贯穿数据库、模型、schema、service、controller、route、前端api/store/page。

## 启动
```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
前端 http://localhost:18244 ；后端 http://localhost:19244/docs ；PostgreSQL localhost:17744，trace / tracepass / operatortrace。结束 `docker compose down -v --remove-orphans` 会删本地数据。

| 角色 | 账号 | 页面与权限 | 动作 |
|---|---|---|---|
| admin | admin@operator.local | 全部含审计 | 复核执行人与完成事件 |
| operator | operator@operator.local | 创建/编辑/执行/导出 | 新建计划并交给worker |
| viewer | viewer@operator.local | 只读和导出 | 观察轨迹，写接口403 |

密码统一 `Trace2026!`。密码PBKDF2，JWT八小时；演示凭据和密钥仅限本地，部署前更换。

## 一天剧本与种子
1. 09:00 operator 登录读取「松原日班温升采样」。
2. 09:05 查看12传感器、240采样，北场/南场/试验间三分区。
3. 09:10 新建 `shift-20261117` 数据集，备注 `daily-readings-20261117.json`。
4. 09:15 保存高于50度→按sensor_id连接→按zone平均的计划。
5. 09:20 提交 `shift-20261117`，观察worker排队到完成。
6. 09:25 逐算子复查输入/输出行数与结果预览。
7. 09:30 导出 `trace-<id>.json`，viewer只读验证。
8. 09:35 用「跨午夜剖面基线」提交 2026-11-17→2026-11-18、Asia/Shanghai 的日加权剖面任务。
9. 09:40 查看各设备覆盖时长与时长加权均值，导出 `profile-<id>.json`。
10. 10:00 admin 查看审计。

seed三账号、四个数据集（240行日班、空数据、重复右键、跨午夜样例）、四个对应计划。固定公式，无随机数；自然键补缺不覆盖用户修改，连续运行不新增。

## 算法与边界
这是教学内核模型，不是PostgreSQL执行器剖面。PostgreSQL真实保存业务元数据；Python worker真实计算表扫描、数值/相等筛选、构建哈希桶与内连接、Decimal累积分组。右表重复键保留倍数，空集合输出空集合。分组avg/sum保留6位小数，输出按规范JSON排序，SHA-256使用排序key紧凑JSON UTF-8；相同输入和计划结果摘要相同。每步输出输入/输出行数、耗时、明细、前5行与checksum。scan 的 input_rows=0 表示从源读取，detail.scanned_rows为扫描源行数；row_visits是扫描/过滤/哈希构建与探测/聚合各步逻辑行访问总和，不代表物理I/O。

DSL最多6步，首步仅scan readings；filter eq/gte/lte；hash_join仅readings.sensor_id=sensors.sensor_id且最多一次；group仅value的count/sum/avg。禁止eval、任意代码和任意SQL。最多100传感器、2000采样、10000连接输出行；超限失败，不保存部分结果。JSON非法、字段错误、非法算子、孤立引用、重复名有可恢复错误。任务使用Redis简单单消费者，进程崩溃后的running任务不自动重试，保留供人工复查后新建任务。

日加权剖面（services/profile_engine.py，纯标准库教学内核）：按受理版快照（数据集+计划的行保留前缀，含group的计划不可剖面）计算每台传感器每个当地日的覆盖时长与时长加权均值。同刻读数先取均值；用后一采样给前值封段，没有后一采样的末采样不计时长；间隔超过一小时的段整段不计，恰好一小时计入；段跨当地午夜按时长分摊，夏令时按实际日长（相邻当地零点的UTC差，23/25小时日如实呈现）；查询单日也取窗外能封段的采样（窗口前最后一个与窗口后第一个折叠采样）。recorded_at为ISO 8601，无时区信息按UTC。中间记录（段/累加器）限500条，超出分批flush，批次数写入结果；每天核齐（全部设备有日记录、覆盖非负且不超当日实际日长、均值落在当日段值域）才出结果。checkpoint逐日单事务落盘，worker重启把未完成任务重新入队从断点恢复，已核齐日期整日跳过，重试不重复累计。单次查询最多62个当地日；时区须为IANA名。

## 技术、目录与本地开发
Python3.11 / FastAPI / SQLAlchemy / psycopg / Redis / PostgreSQL16；原生 HTML/CSS/JS ES modules / nginx1.27。五服务frontend/backend/worker/db/redis均健康探针，命名卷数据库/Redis/共享产物。DB/Redis健康后启动backend，backend健康后启worker/frontend。

backend/src按models/schemas/services/controllers/routes/middlewares/config/constants/utils分层；backend/scripts/seed_demo.py；backend/migrations元数据建表版本。frontend/src按api/stores/pages/components/common/hooks/router/types/constants/utils分层。三共享组件table/status/feedback，两hooks forms/poll。角色/状态/算子枚举在backend/src/constants/enums.py与frontend/src/constants/enums.js；权限/auth、worker状态、operator校验、前端状态展示使用相同枚举值。请求追踪和全局错误中间件、JWT授权、业务审计贯穿模块。

石墨黄铜工程蓝图视觉，双字体Noto Sans SC/Space Mono来自Google Fonts，离线回退；响应桌面/平板/手机。环境变量见.env.example：COMPOSE_PROJECT_NAME、三端口、JWT_SECRET、SEED_DEMO。DATABASE_URL/REDIS_URL由Compose提供。SEED_DEMO启动失败只记日志。

本地后端：pip install -r backend/requirements.txt，设置DATABASE_URL、REDIS_URL、JWT_SECRET，在backend运行uvicorn src.main:app --reload；前端需代理/api，不支持file://。截图、测试、日志和报告在批次根test-artifacts/gb-4105，源码无测试产物。License MIT。
