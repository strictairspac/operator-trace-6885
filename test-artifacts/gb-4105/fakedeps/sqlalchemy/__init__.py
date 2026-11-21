"""最小可用的sqlalchemy假实现：只为在服务层集成测试里驱动真实 src.services.profiles 代码。
覆盖本仓库用到的子集：Column/类型标记/func/ForeignKey、declarative_base、sessionmaker、
create_engine、Session(get/add/commit/refresh/flush/query)、Query(filter_by/order_by/limit/all/first/one/count)。
读时复制、commit时合并：未commit的修改不会进入库，模拟事务回滚。
"""
import copy
DB={}
SEQ={}
class _Type:
 def __init__(self,*a,**k):pass
Integer=String=JSON=DateTime=Text=_Type
def ForeignKey(target):return target
class Column:
 def __init__(self,*args,**kwargs):self.kwargs=kwargs;self.name=None
 def desc(self):return self
 def asc(self):return self
class _Func:
 def now(self):return None
func=_Func()
class _Table:
 def __init__(self,columns):self.columns=columns
class _BaseMeta(type):
 def __new__(mcs,name,bases,ns):
  cls=super().__new__(mcs,name,bases,ns)
  cols=[]
  for k,v in ns.items():
   if isinstance(v,Column):v.name=k;cols.append(v)
  if cols:cls.__table__=_Table(cols)
  return cls
 def __call__(cls,**kw):
  row=super().__call__()
  for c in cls.__table__.columns:setattr(row,c.name,kw.get(c.name,c.kwargs.get('default')))
  return row
class _Metadata:
 def create_all(self,engine):pass
def declarative_base():
 base=_BaseMeta('Base',(),{})
 base.metadata=_Metadata()
 return base
class Query:
 def __init__(self,model,session):self.model=model;self.session=session;self.items=list(DB.setdefault(model.__tablename__,{}).values())
 def filter_by(self,**kw):self.items=[r for r in self.items if all(getattr(r,k)==v for k,v in kw.items())];return self
 def order_by(self,*a):self.items=sorted(self.items,key=lambda r:getattr(r,'id',0) or 0);return self
 def limit(self,n):self.items=self.items[:n];return self
 def all(self):return [self.session._track(self.model,r) for r in self.items]
 def first(self):
  items=self.all();return items[0] if items else None
 def one(self):
  items=self.all();assert len(items)==1,f'期望一行，实际{len(items)}'
  return items[0]
 def count(self):return len(self.items)
class Session:
 fail_at=None;commits=0
 def __init__(self):self._merged=[]
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def _track(self,model,row):
  c=copy.copy(row);self._merged.append((row,c));return c
 def get(self,model,key):
  row=DB.setdefault(model.__tablename__,{}).get(key)
  return self._track(model,row) if row is not None else None
 def add(self,row):
  table=DB.setdefault(row.__tablename__,{})
  if getattr(row,'id',None) is None:
   SEQ[row.__tablename__]=SEQ.get(row.__tablename__,0)+1;row.id=SEQ[row.__tablename__]
  table[row.id]=row
 def commit(self):
  Session.commits+=1
  if Session.fail_at is not None and Session.commits>=Session.fail_at:Session.fail_at=None;raise KeyboardInterrupt('模拟worker进程被杀')
  for orig,c in self._merged:orig.__dict__.update(c.__dict__)
  self._merged.clear()
 def refresh(self,row):pass
 def flush(self):pass
 def query(self,model):return Query(model,self)
def sessionmaker(bind=None):return Session
def create_engine(*a,**k):return object()
