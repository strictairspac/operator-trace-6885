"""按当地日的时长加权均值引擎。

纯Python教学内核：只用标准库，不接触数据库/队列，便于断点恢复与复查。
口径（与课程约定一致）：
- 同一传感器的同刻读数先取均值（Decimal累积，6位小数，与group算子一致）；
- 用后一采样给前值封段：值v_i的有效段为[t_i, t_{i+1})；最后一个采样没有后一采样，不计时长；
- 间隔超过一小时（>3600秒）的段整段不计；恰好3600秒计入；
- 段跨当地午夜按时长分摊到各日；夏令时按实际日长（相邻当地零点的UTC差）；
- 每个查询日都取窗外能封段的采样：窗口前最后一个与窗口后第一个折叠采样；
- 中间记录（段/累加器）内存上限500条，超出分批flush；
- 每天核齐（不变量校验通过）才出结果。
"""
from bisect import bisect_left
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import hashlib,json,math
GAP_SECONDS=3600
BATCH_LIMIT=500
MAX_DAYS=62
class ProfileError(ValueError):pass
def checksum(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def parse_instant(raw,sensor_id):
 """ISO 8601解析为UTC时刻；无时区信息的采样按UTC处理。"""
 if not isinstance(raw,str):raise ProfileError(f'传感器{sensor_id}的recorded_at必须是ISO 8601文本')
 try:dt=datetime.fromisoformat(raw.strip())
 except ValueError:raise ProfileError(f'传感器{sensor_id}的recorded_at无法解析：{raw!r}')
 if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
 return dt.astimezone(timezone.utc)
def select_rows(dataset,steps):
 """应用计划的行保留前缀（scan/filter/hash_join）选取采样；group会破坏时间轴，拒绝。"""
 rows=[dict(r) for r in dataset['readings']]
 for step in steps:
  op=step.get('op')
  if op=='scan':continue
  if op=='group':raise ProfileError('日加权剖面不支持group算子；分组会破坏采样时间轴')
  if op=='filter':
   field,cmp,value=step['field'],step['compare'],step['value']
   def match(row):
    v=row.get(field)
    if cmp=='eq':return v==value
    if not isinstance(v,(int,float)):raise ProfileError('范围比较遇到非数值')
    return v>=value if cmp=='gte' else v<=value
   rows=[r for r in rows if match(r)]
  elif op=='hash_join':
   buckets={}
   for s in dataset['sensors']:buckets.setdefault(s['sensor_id'],[]).append(s)
   rows=[{**r,**s} for r in rows for s in buckets.get(r['sensor_id'],[])]
 return rows
def collapse(rows):
 """同刻读数先取均值；返回{sensor_id:[(时刻,值)]升序}。"""
 by_sensor={}
 for r in rows:
  sid=r.get('sensor_id')
  if not isinstance(sid,int) or isinstance(sid,bool):raise ProfileError('采样缺少有效的sensor_id')
  value=r.get('value')
  if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):raise ProfileError(f'传感器{sid}的value必须是有限数值')
  instant=parse_instant(r.get('recorded_at'),sid)
  by_sensor.setdefault(sid,{}).setdefault(instant,[]).append(Decimal(repr(value)))
 return {sid:[(t,round(float(sum(vs)/len(vs)),6)) for t,vs in sorted(slots.items())] for sid,slots in by_sensor.items()}
def local_days(tz_name,start_date,end_date):
 """当地日序列与各日零点（UTC）；夏令时按实际日长。"""
 try:tz=ZoneInfo(tz_name)
 except Exception:raise ProfileError(f'无效时区：{tz_name!r}；请使用IANA时区名')
 days=[];d=start_date
 while d<=end_date:days.append(d);d+=timedelta(days=1)
 if len(days)>MAX_DAYS:raise ProfileError(f'单次查询最多{MAX_DAYS}个当地日')
 midnights=[datetime(day.year,day.month,day.day,tzinfo=tz).astimezone(timezone.utc) for day in days+[end_date+timedelta(days=1)]]
 return days,midnights
def prepare(snapshot):
 """从受理版快照确定性重建计算上下文；断点恢复走同一路径，保证口径一致。"""
 dataset=snapshot['dataset'];plan=snapshot['plan']
 rows=select_rows(dataset,plan['steps'])
 instants=collapse(rows)
 roster=sorted({s['sensor_id'] for s in dataset['sensors']}|set(instants))
 return {'instants':instants,'times':{sid:[t for t,_ in slots] for sid,slots in instants.items()},'roster':roster,'selected_rows':len(rows),'collapsed':sum(len(v) for v in instants.values())}
def compute_day(ctx,day_start,day_end):
 """核齐一个当地日：取窗外能封段的采样（前一后一），段裁剪到当日窗口，中间记录500条一批。"""
 cells={};batches=0
 for sid in ctx['roster']:
  cov=Decimal(0);svt=Decimal(0);lo_v=None;hi_v=None
  slots=ctx['instants'].get(sid)
  if slots:
   times=ctx['times'][sid]
   i0=bisect_left(times,day_start);i1=bisect_left(times,day_end)
   batch=[]
   def flush():
    nonlocal cov,svt,lo_v,hi_v,batches
    if not batch:return
    for a,b,v in batch:
     secs=Decimal(repr((b-a).total_seconds()))
     cov+=secs;svt+=Decimal(repr(v))*secs
     lo_v=v if lo_v is None else min(lo_v,v);hi_v=v if hi_v is None else max(hi_v,v)
    batch.clear();batches+=1
   for k in range(max(0,i0-1),min(len(slots),i1+1)-1):
    (t0,v0),(t1,_)=slots[k],slots[k+1]
    if (t1-t0).total_seconds()>GAP_SECONDS:continue
    a=t0 if t0>day_start else day_start;b=t1 if t1<day_end else day_end
    if a>=b:continue
    batch.append((a,b,v0))
    if len(batch)>=BATCH_LIMIT:flush()
   flush()
  cells[sid]={'coverage':cov,'sum_vt':svt,'min_v':lo_v,'max_v':hi_v}
 return cells,batches
def reconcile_day(day,day_seconds,cells,roster):
 """每天核齐才出结果：全部设备有日记录、覆盖非负且不超实际日长、均值落在当日段值域。"""
 out=[]
 for sid in roster:
  cell=cells.get(sid)
  if cell is None:raise ProfileError(f'{day}缺少传感器{sid}的日记录，无法核齐')
  cov=cell['coverage']
  if cov<0:raise ProfileError(f'{day}传感器{sid}覆盖时长为负，无法核齐')
  if cov>Decimal(repr(day_seconds))+Decimal('0.000001'):raise ProfileError(f'{day}传感器{sid}覆盖{float(cov)}秒超过当日实际日长{day_seconds}秒，无法核齐')
  mean=None
  if cov>0:
   mean=round(float(cell['sum_vt']/cov),6)
   if cell['min_v'] is not None and not cell['min_v']-1e-6<=mean<=cell['max_v']+1e-6:raise ProfileError(f'{day}传感器{sid}均值越出当日段值域，无法核齐')
  out.append({'sensor_id':sid,'coverage_seconds':round(float(cov),6),'weighted_mean':mean})
 return {'date':day.isoformat(),'day_seconds':day_seconds,'reconciled':True,'sensors':out}
def run_job(ctx,tz_name,start_date,end_date,load,save):
 """逐日核齐驱动：load()读断点，save(day,totals,batches,next_day)每日落一次断点。
 已核齐的日期整日跳过，重试不重复累计；中断后从断点恢复。"""
 days,midnights=local_days(tz_name,start_date,end_date)
 cp=load() or {}
 done={d['date'] for d in cp.get('days',[])}
 totals={int(k):{'coverage':Decimal(v['coverage']),'sum_vt':Decimal(v['sum_vt']),'covered_days':v['covered_days']} for k,v in (cp.get('sensor_totals') or {}).items()}
 batches=cp.get('batches',0)
 for idx,day in enumerate(days):
  key=day.isoformat()
  if key in done:continue
  day_seconds=(midnights[idx+1]-midnights[idx]).total_seconds()
  cells,nb=compute_day(ctx,midnights[idx],midnights[idx+1])
  day_rec=reconcile_day(day,day_seconds,cells,ctx['roster'])
  batches+=nb
  for sid,cell in cells.items():
   t=totals.setdefault(sid,{'coverage':Decimal(0),'sum_vt':Decimal(0),'covered_days':0})
   t['coverage']+=cell['coverage'];t['sum_vt']+=cell['sum_vt']
   if cell['coverage']>0:t['covered_days']+=1
  save(day_rec,{str(k):{'coverage':str(v['coverage']),'sum_vt':str(v['sum_vt']),'covered_days':v['covered_days']} for k,v in totals.items()},batches,days[idx+1].isoformat() if idx+1<len(days) else None)
def finalize_result(ctx,snapshot,tz_name,start_date,end_date,checkpoint,duration_ms):
 """装配最终结果：逐日明细 + 各设备覆盖时长与时长加权均值汇总。"""
 days=sorted(checkpoint['days'],key=lambda d:d['date'])
 totals={int(k):v for k,v in (checkpoint.get('sensor_totals') or {}).items()}
 info={}
 for s in snapshot['dataset']['sensors']:info.setdefault(s['sensor_id'],{'zone':s.get('zone'),'device_type':s.get('device_type')})
 sensors=[]
 for sid in ctx['roster']:
  t=totals.get(sid);cov=Decimal(t['coverage']) if t else Decimal(0)
  sensors.append({'sensor_id':sid,'zone':(info.get(sid) or {}).get('zone'),'device_type':(info.get(sid) or {}).get('device_type'),'coverage_seconds':round(float(cov),6),'covered_days':t['covered_days'] if t else 0,'weighted_mean':round(float(Decimal(t['sum_vt'])/cov),6) if t and cov>0 else None})
 result={'timezone':tz_name,'start_date':start_date.isoformat(),'end_date':end_date.isoformat(),'gap_seconds':GAP_SECONDS,'batch_limit':BATCH_LIMIT,'batches':checkpoint.get('batches',0),'days':days,'sensors':sensors,'totals':{'days':len(days),'reconciled_days':len(days),'sensors':len(ctx['roster']),'selected_rows':ctx['selected_rows'],'collapsed_instants':ctx['collapsed']},'source':{'dataset':snapshot['dataset']['name'],'plan':snapshot['plan']['name']},'duration_ms':duration_ms,'limits':{'batch_limit':BATCH_LIMIT,'max_days':MAX_DAYS,'gap_seconds':GAP_SECONDS,'max_sensors':100,'max_readings':2000},'model':'按当地日的时长加权均值教学内核；PostgreSQL仅保存业务元数据'}
 result['checksum']=checksum({'days':days,'sensors':sensors})
 return result
