"""日加权剖面引擎测试：纯标准库，直接驱动 backend/src/services/profile_engine.py。

运行：python3 test_profile_engine.py
覆盖：同刻均值、后一采样封段、超一小时整段不计、跨午夜分摊、夏令时实际日长、
窗外封段采样、500条分批、断点恢复幂等、计划行保留前缀、可恢复错误。
"""
import sys
from datetime import date
sys.path.insert(0,'/workspace/backend')
from src.services import profile_engine as eng

PASSED=[]
def check(name,cond,info=''):
 if not cond:raise AssertionError(f'{name} {info}')
 PASSED.append(name)

def snap(readings,sensors=None,steps=None):
 return {'dataset':{'id':1,'name':'t','description':'','sensors':sensors if sensors is not None else[{'sensor_id':1,'zone':'北场','device_type':'pump'},{'sensor_id':2,'zone':'南场','device_type':'motor'},{'sensor_id':3,'zone':'试验间','device_type':'valve'}],'readings':readings},'plan':{'id':1,'name':'p','dataset_id':1,'steps':steps if steps is not None else[{'op':'scan','source':'readings'}],'note':''}}

def run(snapshot,tz,start,end,boom_after=None):
 """内存版process_job：模拟逐日核齐与断点落盘；boom_after用于注入第N日后的崩溃。"""
 ctx=eng.prepare(snapshot)
 store={'cp':None}
 calls={'n':0}
 def load():return store['cp']
 def save(day_rec,totals,batches,next_day):
  days=list((store['cp'] or {}).get('days',[]))
  assert day_rec['date'] not in {d['date'] for d in days},'重复累计：同一日期被写入两次'
  days.append(day_rec)
  store['cp']={'days':days,'sensor_totals':totals,'batches':batches,'next_day':next_day}
  calls['n']+=1
  if boom_after is not None and calls['n']==boom_after:raise RuntimeError('模拟worker崩溃')
 try:
  eng.run_job(ctx,tz,start,end,load,save)
 except RuntimeError:
  eng.run_job(ctx,tz,start,end,load,save)  # 断点恢复
 return eng.finalize_result(ctx,snapshot,tz,start,end,store['cp'],1.0)

def cell(result,day,sid):
 d=next(x for x in result['days'] if x['date']==day)
 return next(s for s in d['sensors'] if s['sensor_id']==sid)
def dev(result,sid):return next(s for s in result['sensors'] if s['sensor_id']==sid)

# 跨午夜样例（与种子数据集同构，UTC采样）
X=[{'sensor_id':1,'value':10,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':1,'value':20,'recorded_at':'2026-11-17T22:30:00'},{'sensor_id':1,'value':30,'recorded_at':'2026-11-17T23:30:00'},{'sensor_id':1,'value':40,'recorded_at':'2026-11-18T00:30:00'},{'sensor_id':1,'value':50,'recorded_at':'2026-11-18T01:00:00'},{'sensor_id':2,'value':100,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':2,'value':300,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':2,'value':200,'recorded_at':'2026-11-17T22:45:00'},{'sensor_id':2,'value':60,'recorded_at':'2026-11-18T05:00:00'},{'sensor_id':3,'value':8,'recorded_at':'2026-11-16T23:40:00'},{'sensor_id':3,'value':12,'recorded_at':'2026-11-17T00:20:00'},{'sensor_id':3,'value':16,'recorded_at':'2026-11-17T00:50:00'}]

r=run(snap(X),'UTC',date(2026,11,17),date(2026,11,18))
c=cell(r,'2026-11-17',1);check('跨午夜-前日覆盖',c['coverage_seconds']==7200 and c['weighted_mean']==20.0,c)
c=cell(r,'2026-11-18',1);check('跨午夜-后日分摊',c['coverage_seconds']==3600 and c['weighted_mean']==35.0,c)
c=cell(r,'2026-11-17',2);check('同刻读数先取均值',c['coverage_seconds']==2700 and c['weighted_mean']==200.0,c)
c=cell(r,'2026-11-18',2);check('末采样无后一采样不计',c['coverage_seconds']==0 and c['weighted_mean'] is None,c)
c=cell(r,'2026-11-17',3);check('窗外采样封段（窗口前）',c['coverage_seconds']==3000 and c['weighted_mean']==10.4,c)
d=dev(r,1);check('设备汇总-覆盖与均值',d['coverage_seconds']==10800 and d['weighted_mean']==25.0 and d['covered_days']==2,d)
d=dev(r,3);check('设备汇总-区域信息',d['zone']=='试验间' and d['device_type']=='valve',d)
check('每天核齐才出结果',all(x['reconciled'] for x in r['days']) and r['totals']['reconciled_days']==2)

# 查一天也要取窗外能封段的采样：23:30的段由次日00:30（窗外）封段
r1=run(snap(X),'UTC',date(2026,11,17),date(2026,11,17))
c=cell(r1,'2026-11-17',1);check('单日查询-窗外后一采样封段',c['coverage_seconds']==7200 and c['weighted_mean']==20.0,c)
check('单日查询-只有一天',len(r1['days'])==1)

# 当地日与时区：同一批UTC采样在Asia/Shanghai下落到不同当地日
r2=run(snap(X),'Asia/Shanghai',date(2026,11,17),date(2026,11,18))
c=cell(r2,'2026-11-17',3);check('当地日-上海前日',c['coverage_seconds']==4200 and c['weighted_mean']==9.714286,c)
c=cell(r2,'2026-11-18',1);check('当地日-上海后日',c['coverage_seconds']==10800 and c['weighted_mean']==25.0,c)
c=cell(r2,'2026-11-17',1);check('当地日-上海前日零覆盖',c['coverage_seconds']==0 and c['weighted_mean'] is None,c)

# 夏令时按实际日长：America/New_York 2026-03-08=23h，2026-11-01=25h
DST=[{'sensor_id':1,'value':5,'recorded_at':'2026-03-08T04:30:00Z'},{'sensor_id':1,'value':7,'recorded_at':'2026-03-08T05:30:00Z'},{'sensor_id':1,'value':10,'recorded_at':'2026-03-08T06:00:00Z'},{'sensor_id':1,'value':20,'recorded_at':'2026-03-08T06:45:00Z'}]
r3=run(snap(DST,sensors=[{'sensor_id':1,'zone':'北场','device_type':'pump'}]),'America/New_York',date(2026,3,7),date(2026,3,8))
d7=next(x for x in r3['days'] if x['date']=='2026-03-07');d8=next(x for x in r3['days'] if x['date']=='2026-03-08')
check('夏令时-春季23小时',d8['day_seconds']==82800.0,d8['day_seconds'])
c=d8['sensors'][0];check('夏令时-跨午夜分摊到实际日',c['coverage_seconds']==6300 and c['weighted_mean']==7.714286,c)
c=d7['sensors'][0];check('夏令时-前日片段',c['coverage_seconds']==1800 and c['weighted_mean']==5.0,c)
days,_=eng.local_days('America/New_York',date(2026,11,1),date(2026,11,1))
check('夏令时-秋季25小时',(_[1]-_[0]).total_seconds()==90000.0)

# 恰好3600秒计入，3601秒整段不计
GAP=[{'sensor_id':1,'value':1,'recorded_at':'2026-11-17T00:00:00'},{'sensor_id':1,'value':2,'recorded_at':'2026-11-17T01:00:00'},{'sensor_id':1,'value':3,'recorded_at':'2026-11-17T02:00:01'},{'sensor_id':1,'value':4,'recorded_at':'2026-11-17T02:30:00'}]
r4=run(snap(GAP,sensors=[{'sensor_id':1,'zone':'北场','device_type':'pump'}]),'UTC',date(2026,11,17),date(2026,11,17))
c=cell(r4,'2026-11-17',1);check('一小时边界',c['coverage_seconds']==5399 and c['weighted_mean']==round(8997/5399,6),c)

# 中间记录500条一批：601个采样=600段，应分2批，结果与不分批一致
MANY=[{'sensor_id':1,'value':7,'recorded_at':f'2026-11-17T{h:02d}:{m:02d}:00'} for h in range(10) for m in range(60)]+[{'sensor_id':1,'value':7,'recorded_at':'2026-11-17T10:00:00'}]
r5=run(snap(MANY,sensors=[{'sensor_id':1,'zone':'北场','device_type':'pump'}]),'UTC',date(2026,11,17),date(2026,11,17))
c=cell(r5,'2026-11-17',1);check('分批-结果一致',c['coverage_seconds']==36000 and c['weighted_mean']==7.0,c)
check('分批-500条一批',r5['batches']==2,r5['batches'])

# 断点恢复：第1日核齐后崩溃，恢复后结果与一气呵成一致；重试不重复累计
full=run(snap(X),'UTC',date(2026,11,17),date(2026,11,18))
resumed=run(snap(X),'UTC',date(2026,11,17),date(2026,11,18),boom_after=1)
check('断点恢复-结果一致',full['checksum']==resumed['checksum'])
ctx=eng.prepare(snap(X));store={'cp':None}
def load():return store['cp']
def save(d,t,b,n):store['cp']={'days':store['cp']['days']+[d] if store['cp'] else [d],'sensor_totals':t,'batches':b,'next_day':n}
eng.run_job(ctx,'UTC',date(2026,11,17),date(2026,11,18),load,save)
before=store['cp']
eng.run_job(ctx,'UTC',date(2026,11,17),date(2026,11,18),load,save)  # 重复触发：已核齐日期整日跳过
check('重试不重复累计',store['cp']==before and len(store['cp']['days'])==2)

# 计划行保留前缀：filter生效；hash_join重复右键被同刻均值中和；group拒绝
rf=run(snap(X,steps=[{'op':'scan','source':'readings'},{'op':'filter','field':'value','compare':'gte','value':15}]),'UTC',date(2026,11,17),date(2026,11,17))
c=cell(rf,'2026-11-17',1);check('计划前缀-filter生效',c['coverage_seconds']==5400 and c['weighted_mean']==round(126000/5400,6),c)
dup_sensors=[{'sensor_id':1,'zone':'北场','device_type':'pump'},{'sensor_id':1,'zone':'复核点','device_type':'pump'},{'sensor_id':2,'zone':'南场','device_type':'motor'},{'sensor_id':3,'zone':'试验间','device_type':'valve'}]
rj=run(snap(X,sensors=dup_sensors,steps=[{'op':'scan','source':'readings'},{'op':'hash_join','right':'sensors','left_key':'sensor_id','right_key':'sensor_id'}]),'UTC',date(2026,11,17),date(2026,11,17))
c=cell(rj,'2026-11-17',1);check('计划前缀-重复右键不重复计时长',c['coverage_seconds']==7200 and c['weighted_mean']==20.0,c)
try:
 eng.prepare(snap(X,steps=[{'op':'scan','source':'readings'},{'op':'group','keys':['zone'],'measure':'value','aggregate':'avg'}]));check('group拒绝',False)
except eng.ProfileError as e:check('group拒绝','group' in str(e))

# 可恢复错误与边界
for bad,msg in [([{'sensor_id':1,'value':1,'recorded_at':'not-a-time'}],'无法解析'),([{'sensor_id':1,'value':1,'recorded_at':None}],'ISO 8601')]:
 try:run(snap(bad,sensors=[{'sensor_id':1,'zone':'z','device_type':'pump'}]),'UTC',date(2026,11,17),date(2026,11,17));check('错误'+msg,False)
 except eng.ProfileError as e:check('错误'+msg,msg in str(e),e)
try:eng.local_days('Not/AZone',date(2026,11,17),date(2026,11,17));check('无效时区',False)
except eng.ProfileError as e:check('无效时区','无效时区' in str(e))
try:eng.local_days('UTC',date(2026,1,1),date(2026,4,1));check('62天上限',False)
except eng.ProfileError as e:check('62天上限','62' in str(e))

# 空数据集：空集合输出空集合，每天仍核齐
re_=run(snap([],sensors=[]),'UTC',date(2026,11,17),date(2026,11,18))
check('空数据集',re_['sensors']==[] and all(d['sensors']==[] for d in re_['days']) and re_['totals']['reconciled_days']==2)

# 确定性：相同输入相同摘要
check('摘要确定性',run(snap(X),'UTC',date(2026,11,17),date(2026,11,18))['checksum']==full['checksum'])

print(f'全部通过：{len(PASSED)}项')
for name in PASSED:print(' ✓',name)
