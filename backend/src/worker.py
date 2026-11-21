import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.trace import Trace
from src.models.profile import Profile
from src.services.operators import execute
from src.services import profiles
from src.services.audit import log
q=redis.Redis.from_url(REDIS_URL)
def requeue_interrupted():
 """worker重启后把未完成的剖面任务重新入队，从断点恢复；trace任务保持人工复查口径，不自动重试。"""
 try:
  with Session() as s:ids=[r.id for r in s.query(Profile).filter(Profile.status.in_(('queued','running'))).all()]
  for run_id in ids:q.rpush('operator-profiles',run_id)
  if ids:logging.info('requeued %s interrupted profile jobs',len(ids))
 except Exception:logging.exception('profile requeue failed')
requeue_interrupted()
while True:
 Path('/tmp/worker-heartbeat').touch()
 try:
  item=q.blpop(['operator-traces','operator-profiles'],timeout=2)
  if not item:continue
  source=item[0].decode() if isinstance(item[0],bytes) else item[0];run_id=int(item[1])
  if source=='operator-profiles':
   profiles.process_job(run_id);continue
  with Session() as s:
   row=s.get(Trace,run_id)
   if not row or row.status!='queued':continue
   row.status='running';snapshot=row.snapshot;s.commit()
  try:
   result=execute(snapshot['dataset'],snapshot['plan']['steps'])
   with Session() as s:r=s.get(Trace,run_id);r.result=result;r.status='completed';s.commit()
   log('worker','trace.completed',str(run_id))
  except Exception as exc:
   logging.exception('trace failed')
   with Session() as s:r=s.get(Trace,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
 except Exception:logging.exception('worker loop');time.sleep(2)
