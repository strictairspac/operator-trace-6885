from sqlalchemy import declarative_base
class sessionmaker:
 def __init__(self,bind=None):pass
 def __call__(self):
  from sqlalchemy import Session
  return Session()
