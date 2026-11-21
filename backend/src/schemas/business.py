from pydantic import BaseModel,Field,model_validator,ConfigDict
from typing import Literal
from datetime import date
from zoneinfo import ZoneInfo
from src.services.operators import validate_steps
from src.services.profile_engine import MAX_DAYS
class Login(BaseModel):
 email:str;password:str
class Sensor(BaseModel):
 model_config=ConfigDict(extra='forbid')
 sensor_id:int=Field(ge=1,le=100000)
 zone:str=Field(min_length=1,max_length=40)
 device_type:Literal['pump','motor','valve']
class Reading(BaseModel):
 model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
 sensor_id:int=Field(ge=1,le=100000)
 value:float=Field(ge=-1000000,le=1000000)
 recorded_at:str=Field(min_length=1,max_length=40)
class DatasetInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 description:str=Field(default='',max_length=500)
 sensors:list[Sensor]=Field(max_length=100)
 readings:list[Reading]=Field(max_length=2000)
class PlanInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 dataset_id:int
 steps:list[dict]
 note:str=Field(default='',max_length=500)
 @model_validator(mode='after')
 def validate(self):validate_steps(self.steps);return self
class TraceInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 plan_id:int
class ProfileInput(BaseModel):
 name:str=Field(min_length=2,max_length=120)
 plan_id:int
 start_date:date
 end_date:date
 timezone:str=Field(min_length=1,max_length=40)
 @model_validator(mode='after')
 def validate(self):
  if self.end_date<self.start_date:raise ValueError('截止日不能早于起始日')
  if (self.end_date-self.start_date).days>MAX_DAYS-1:raise ValueError(f'单次查询最多覆盖{MAX_DAYS}个当地日')
  try:ZoneInfo(self.timezone)
  except Exception:raise ValueError('无效时区；请使用IANA时区名，例如Asia/Shanghai')
  return self
