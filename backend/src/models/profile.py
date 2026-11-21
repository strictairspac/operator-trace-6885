from sqlalchemy import Column,Integer,String,JSON,DateTime,func,ForeignKey
from src.config.database import Base
class Profile(Base):
 __tablename__='profiles'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 dataset_id=Column(Integer,ForeignKey('datasets.id'),nullable=False)
 plan_id=Column(Integer,ForeignKey('plans.id'),nullable=False)
 tz=Column(String(40),nullable=False)
 start_date=Column(String(10),nullable=False)
 end_date=Column(String(10),nullable=False)
 status=Column(String(20),default='queued',nullable=False)
 result=Column(JSON,nullable=True)
 error=Column(String(1000),nullable=True)
 checkpoint=Column(JSON,nullable=True)
 snapshot=Column(JSON,nullable=False)
 created_at=Column(DateTime,server_default=func.now())
