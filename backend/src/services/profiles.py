import logging,time,redis
from datetime import date
from fastapi import HTTPException
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.profile import Profile
from src.services import profile_engine as eng
from src.services.audit import log
from src.utils.serialization import record
queue=redis.Redis.from_url(REDIS_URL)
def list_items():
 with Session() as s:return [record(r) for r in s.query(Profile).order_by(Profile.id.desc()).limit(100).all()]
def detail(item_id):
 with Session() as s:
  row=s.get(Profile,item_id)
  if not row:raise HTTPException(404,'未找到日加权剖面')
  return record(row)
def create(data):
 with Session() as s:
  p=s.get(Plan,data.plan_id)
  if not p:raise HTTPException(404,'未找到算子计划')
  if any(step.get('op')=='group' for step in p.steps):raise HTTPException(400,'日加权剖面不支持含group算子的计划；分组会破坏采样时间轴')
  d=s.get(Dataset,p.dataset_id)
  row=Profile(name=data.name,plan_id=p.id,dataset_id=d.id,tz=data.timezone,start_date=data.start_date.isoformat(),end_date=data.end_date.isoformat(),status='queued',snapshot={'dataset':record(d),'plan':record(p)})
  s.add(row);s.commit();s.refresh(row);result=record(row)
 try:queue.rpush('operator-profiles',result['id'])
 except redis.RedisError:
  with Session() as s:r=s.get(Profile,result['id']);r.status='failed';r.error='队列不可用，请创建新任务';s.commit()
  raise HTTPException(503,'队列不可用，请稍后重试')
 return result
def process_job(profile_id):
 """逐日核齐，每日一个事务落断点；中断后从断点恢复，重试不重复累计。"""
 with Session() as s:
  row=s.get(Profile,profile_id)
  if not row or row.status not in ('queued','running'):return
  row.status='running';s.commit()
  snapshot=row.snapshot;tz_name=row.tz;start=date.fromisoformat(row.start_date);end=date.fromisoformat(row.end_date)
 started=time.perf_counter()
 try:
  ctx=eng.prepare(snapshot)
  total_days=len(eng.local_days(tz_name,start,end)[0])
  def load():
   with Session() as s:
    r=s.get(Profile,profile_id)
    return r.checkpoint if r and r.checkpoint else None
  def save(day_rec,totals_json,batches,next_day):
   with Session() as s:
    r=s.get(Profile,profile_id)
    days=list((r.checkpoint or {}).get('days',[]))
    if day_rec['date'] in {d['date'] for d in days}:return
    r.checkpoint={'days':days+[day_rec],'sensor_totals':totals_json,'batches':batches,'next_day':next_day,'reconciled_days':len(days)+1,'total_days':total_days}
    s.commit()
  eng.run_job(ctx,tz_name,start,end,load,save)
  with Session() as s:
   r=s.get(Profile,profile_id)
   r.result=eng.finalize_result(ctx,snapshot,tz_name,start,end,r.checkpoint,round((time.perf_counter()-started)*1000,4))
   r.status='completed';s.commit()
  log('worker','profile.completed',str(profile_id))
 except Exception as exc:
  logging.exception('profile failed')
  with Session() as s:r=s.get(Profile,profile_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
