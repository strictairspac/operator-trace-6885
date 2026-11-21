from src.config.database import Base,engine,Session
from src.models.identity import User,Audit
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.trace import Trace
from src.models.profile import Profile
from src.utils.security import hash_password
DEFAULT_STEPS=[{'op':'scan','source':'readings'},{'op':'filter','field':'value','compare':'gte','value':50},{'op':'hash_join','right':'sensors','left_key':'sensor_id','right_key':'sensor_id'},{'op':'group','keys':['zone'],'measure':'value','aggregate':'avg'}]
PROFILE_STEPS=[{'op':'scan','source':'readings'},{'op':'hash_join','right':'sensors','left_key':'sensor_id','right_key':'sensor_id'}]
def seed():
 Base.metadata.create_all(engine)
 with Session() as s:
  for role in ('admin','operator','viewer'):
   if not s.query(User).filter_by(email=role+'@operator.local').first():s.add(User(email=role+'@operator.local',role=role,password=hash_password('Trace2026!')))
  sensors=[{'sensor_id':i,'zone':['北场','南场','试验间'][i%3],'device_type':['pump','motor','valve'][i%3]} for i in range(1,13)]
  readings=[{'sensor_id':i%12+1,'value':round(25+(i*13%800)/10,1),'recorded_at':f'2026-11-17T{8+i//60:02d}:{i%60:02d}:00'} for i in range(240)]
  xsensors=[{'sensor_id':1,'zone':'北场','device_type':'pump'},{'sensor_id':2,'zone':'南场','device_type':'motor'},{'sensor_id':3,'zone':'试验间','device_type':'valve'}]
  xreadings=[{'sensor_id':1,'value':10,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':1,'value':20,'recorded_at':'2026-11-17T22:30:00'},{'sensor_id':1,'value':30,'recorded_at':'2026-11-17T23:30:00'},{'sensor_id':1,'value':40,'recorded_at':'2026-11-18T00:30:00'},{'sensor_id':1,'value':50,'recorded_at':'2026-11-18T01:00:00'},{'sensor_id':2,'value':100,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':2,'value':300,'recorded_at':'2026-11-17T22:00:00'},{'sensor_id':2,'value':200,'recorded_at':'2026-11-17T22:45:00'},{'sensor_id':2,'value':60,'recorded_at':'2026-11-18T05:00:00'},{'sensor_id':3,'value':8,'recorded_at':'2026-11-16T23:40:00'},{'sensor_id':3,'value':12,'recorded_at':'2026-11-17T00:20:00'},{'sensor_id':3,'value':16,'recorded_at':'2026-11-17T00:50:00'}]
  seeds=[('松原日班温升采样',sensors,readings,'240条采样 / 12个传感器 / 区域温升复核'),('空数据边界',[],[],'验证空输入和空聚合'),('重复键校验',[{'sensor_id':1,'zone':'北场','device_type':'pump'},{'sensor_id':1,'zone':'复核点','device_type':'pump'}],[{'sensor_id':1,'value':80,'recorded_at':'2026-11-17T09:00:00'}],'右表重复键必须保留连接倍数'),('松原跨午夜采样',xsensors,xreadings,'跨午夜分摊 / 同刻重复 / 超一小时间隔 / 窗外封段样例（UTC采样）')]
  for name,a,b,desc in seeds:
   if not s.query(Dataset).filter_by(name=name).first():s.add(Dataset(name=name,sensors=a,readings=b,description=desc))
  s.flush()
  plans=[('过滤-连接-分组基线','松原日班温升采样',DEFAULT_STEPS,'受限DSL，Python算子真实执行'),('空输入管线','空数据边界',DEFAULT_STEPS,'受限DSL，Python算子真实执行'),('重复键内连接','重复键校验',DEFAULT_STEPS,'受限DSL，Python算子真实执行'),('跨午夜剖面基线','松原跨午夜采样',PROFILE_STEPS,'行保留前缀（无group），供日加权剖面选取采样')]
  for pname,dname,steps,note in plans:
   if not s.query(Plan).filter_by(name=pname).first():s.add(Plan(name=pname,dataset_id=s.query(Dataset).filter_by(name=dname).one().id,steps=steps,note=note))
  s.commit();counts={m.__tablename__:s.query(m).count() for m in (User,Dataset,Plan,Trace,Profile)};print(counts);return counts
if __name__=='__main__':seed()
