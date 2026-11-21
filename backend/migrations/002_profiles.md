# Schema v2

Adds `profiles`: 日加权剖面任务。每行保存受理版快照（dataset+plan）、IANA时区与起止日、断点checkpoint（已核齐的日、设备累计、批次数、下一待核齐日）与最终结果。自然键name唯一；status沿用queued/running/completed/failed枚举。SQLAlchemy metadata create_all；PostgreSQL只持久化业务元数据，时长加权均值由Python教学内核计算。
