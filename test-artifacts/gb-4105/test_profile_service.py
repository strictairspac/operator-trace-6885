"""服务层集成测试：用fakedeps里的最小假实现驱动真实 src.services.profiles 代码。

验证：受理版快照入队、逐日核齐落断点、状态流转、worker崩溃（KeyboardInterrupt模拟进程被杀，
不进入failed）后从断点恢复且重试不重复累计、结果与引擎口径一致、group计划拒绝。
运行：python3 test_profile_service.py
"""
import os,sys,types
os.environ['JWT_SECRET']='test-secret'
sys.path.insert(0,'/workspace/test-artifacts/gb-4105/fakedeps')
sys.path.insert(0,'/workspace/backend')
from datetime import date
import sqlalchemy,redis
from src.config.database import Session
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.services import profiles

PASSED=[]
def check(name,cond,info=''):
 if not cond:raise AssertionError(f'{name} {info}')
 PASSED.append(name)

SENSORS=[{'sensor_id':1,'zone':'北场','device_type':'pump'},{'sensor_id':2,'zone':'南场','device_type':'motor'},{'sensor_id':3,'zone':'试验间','device_type':'valve'}]
X=[{'sensor_id':1,'value':10,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':1,'value':20,'recorded_at':'2026-11-17T22:30:00'},{'sensor_id':1,'value':30,'recorded_at':'2026-11-17T23:30:00'},{'sensor_id':1,'value':40,'recorded_at':'2026-11-18T00:30:00'},{'sensor_id':1,'value':50,'recorded_at':'2026-11-18T01:00:00'},{'sensor_id':2,'value':100,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':2,'value':300,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':2,'value':200,'recorded_at':'2026-11-17T22:45:00'},{'sensor_id':2,'value':60,'recorded_at':'2026-11-18T05:00:00'},{'sensor_id':3,'value':8,'recorded_at':'2026-11-16T23:40:00'},{'sensor_id':3,'value':12,'recorded_at':'2026-11-17T00:20:00'},{'sensor_id':3,'value':16,'recorded_at':'2026-11-17T00:50:00'}]
STEPS=[{'op':'scan','source':'readings'},{'op':'hash_join','right':'sensors','left_key':'sensor_id','right_key':'sensor_id'}]
with Session() as s:
 s.add(Dataset(name='松原跨午夜采样',description='',sensors=SENSORS,readings=X))
 s.add(Plan(name='跨午夜剖面基线',dataset_id=1,steps=STEPS,note=''))
 s.add(Plan(name='含group的计划',dataset_id=1,steps=STEPS+[{'op':'group','keys':['zone'],'measure':'value','aggregate':'avg'}],note=''))
 s.commit()

def req(name,tz='UTC',start=date(2026,11,17),end=date(2026,11,18),plan_id=1):
 return types.SimpleNamespace(name=name,plan_id=plan_id,timezone=tz,start_date=start,end_date=end)

# 受理：快照+入队
r=profiles.create(req('profile-a'))
check('受理后排队',r['status']=='queued' and r['tz']=='UTC')
check('受理版快照',r['snapshot']['dataset']['name']=='松原跨午夜采样' and r['snapshot']['plan']['steps']==STEPS)
check('已入队',redis.PUSHED[-1]==('operator-profiles',r['id']))

# 完整执行：逐日核齐，每日一个断点
profiles.process_job(r['id'])
d=profiles.detail(r['id'])
check('执行完成',d['status']=='completed')
check('断点核齐计数',d['checkpoint']['reconciled_days']==2 and d['checkpoint']['total_days']==2)
res=d['result']
day17=next(x for x in res['days'] if x['date']=='2026-11-17')
s1=next(c for c in day17['sensors'] if c['sensor_id']==1)
check('服务口径-跨午夜前日',s1['coverage_seconds']==7200 and s1['weighted_mean']==20.0,s1)
day18=next(x for x in res['days'] if x['date']=='2026-11-18')
s1b=next(c for c in day18['sensors'] if c['sensor_id']==1)
check('服务口径-跨午夜后日',s1b['coverage_seconds']==3600 and s1b['weighted_mean']==35.0,s1b)
dev1=next(x for x in res['sensors'] if x['sensor_id']==1)
check('服务口径-设备汇总',dev1['coverage_seconds']==10800 and dev1['weighted_mean']==25.0 and dev1['zone']=='北场',dev1)
check('结果摘要存在',len(res['checksum'])==64)

# 重复触发不重复执行
profiles.process_job(r['id'])
check('已完成任务不重跑',profiles.detail(r['id'])['result']['checksum']==res['checksum'])

# worker崩溃（进程被杀，不标failed）后从断点恢复
r2=profiles.create(req('profile-b'))
sqlalchemy.Session.commits=0;sqlalchemy.Session.fail_at=3  # 第3次commit＝第2天checkpoint落盘时进程被杀
try:
 profiles.process_job(r2['id']);check('崩溃注入',False)
except KeyboardInterrupt:pass
mid=profiles.detail(r2['id'])
check('崩溃后保持running',mid['status']=='running')
check('断点只含已核齐日',[x['date'] for x in mid['checkpoint']['days']]==['2026-11-17'])
profiles.process_job(r2['id'])
d2=profiles.detail(r2['id'])
check('断点恢复完成',d2['status']=='completed')
check('恢复后不重累计',[x['date'] for x in d2['checkpoint']['days']]==['2026-11-17','2026-11-18'])
check('恢复结果与一气呵成一致',d2['result']['checksum']==res['checksum'])

# 可恢复错误：group计划与未知计划
try:
 profiles.create(req('profile-c',plan_id=2));check('group计划拒绝',False)
except Exception as e:check('group计划拒绝',getattr(e,'status_code',None)==400 and 'group' in str(e.detail),e)
try:
 profiles.create(req('profile-d',plan_id=999));check('未知计划404',False)
except Exception as e:check('未知计划404',getattr(e,'status_code',None)==404,e)

# 坏数据：任务失败并给出可恢复错误
with Session() as s:
 s.add(Dataset(name='坏时间戳',description='',sensors=[{'sensor_id':1,'zone':'z','device_type':'pump'}],readings=[{'sensor_id':1,'value':1,'recorded_at':'bad'}]))
 s.add(Plan(name='坏数据计划',dataset_id=2,steps=[{'op':'scan','source':'readings'}],note=''))
 s.commit()
r3=profiles.create(req('profile-e',plan_id=3))
profiles.process_job(r3['id'])
d3=profiles.detail(r3['id'])
check('坏数据任务失败',d3['status']=='failed' and '无法解析' in (d3['error'] or ''),d3['error'])

check('列表接口',len(profiles.list_items())==3)
print(f'全部通过：{len(PASSED)}项')
for name in PASSED:print(' ✓',name)
