"""种子脚本测试：在fakedeps上运行真实 scripts.seed_demo，验证幂等与跨午夜样例内容。
运行：python3 test_seed.py
"""
import os,sys
os.environ['JWT_SECRET']='test-secret'
sys.path.insert(0,'/workspace/test-artifacts/gb-4105/fakedeps')
sys.path.insert(0,'/workspace/backend')
from src.config.database import Session
from src.models.dataset import Dataset
from src.models.plan import Plan
from scripts.seed_demo import seed

PASSED=[]
def check(name,cond,info=''):
 if not cond:raise AssertionError(f'{name} {info}')
 PASSED.append(name)

first=seed()
second=seed()
check('幂等-连续运行不新增',first==second,(first,second))
check('账号与实体数量',first['users']==3 and first['datasets']==4 and first['plans']==4,first)
with Session() as s:
 d=s.query(Dataset).filter_by(name='松原跨午夜采样').one()
 check('跨午夜样例行数',len(d.sensors)==3 and len(d.readings)==12)
 check('同刻重复样例',sum(1 for r in d.readings if r['sensor_id']==2 and r['recorded_at']=='2026-11-17T22:00:00')==2)
 check('窗外封段样例',any(r['recorded_at']=='2026-11-16T23:40:00' for r in d.readings))
 p=s.query(Plan).filter_by(name='跨午夜剖面基线').one()
 check('剖面基线无group',all(step['op']!='group' for step in p.steps) and p.dataset_id==d.id)
print(f'全部通过：{len(PASSED)}项')
for name in PASSED:print(' ✓',name)
