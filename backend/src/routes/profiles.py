import json
from fastapi import APIRouter,Depends
from fastapi.responses import Response
from src.middlewares.auth import current,writer
from src.schemas.business import ProfileInput
from src.services import profiles
from src.controllers.business import start_profile
router=APIRouter()
@router.get('/profiles')
def listing(u=Depends(current)):return profiles.list_items()
@router.post('/profiles')
def create(data:ProfileInput,u=Depends(writer)):return start_profile(data,u)
@router.get('/profiles/{item_id}')
def detail(item_id:int,u=Depends(current)):return profiles.detail(item_id)
@router.get('/profiles/{item_id}/export')
def export(item_id:int,u=Depends(current)):
 return Response(json.dumps(profiles.detail(item_id),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="profile-{item_id}.json"'})
