"""Lightweight daily scheduler; schedules are opt-in and persisted locally."""
from __future__ import annotations
import json, time, uuid, threading
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .main import orchestrate, ChatIn, event
router=APIRouter(prefix="/api/schedules",tags=["schedules"])
FILE=Path(__file__).resolve().parent.parent/"data"/"schedules.json"
TZ="Asia/Kathmandu"
def load():
 try:return json.loads(FILE.read_text())
 except:return []
def save(x):FILE.write_text(json.dumps(x,indent=2))
class ScheduleIn(BaseModel):
 name:str
 prompt:str
 time:str=Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
 enabled:bool=True
class Toggle(BaseModel):enabled:bool
@router.get("")
async def get_schedules():return load()
@router.post("")
async def add(s:ScheduleIn):
 a=load();item={"id":str(uuid.uuid4())[:8],**s.model_dump(),"created":time.time(),"last_run_date":None}
 a.append(item);save(a);event("schedule_created",item);return item
@router.patch("/{sid}")
async def toggle(sid:str,b:Toggle):
 a=load();s=next((x for x in a if x["id"]==sid),None)
 if not s:raise HTTPException(404,"Schedule not found")
 s["enabled"]=b.enabled;save(a);event("schedule_toggled",{"id":sid,"enabled":b.enabled});return s
@router.delete("/{sid}")
async def delete(sid:str):
 a=load();n=[x for x in a if x["id"]!=sid]
 if len(n)==len(a):raise HTTPException(404,"Schedule not found")
 save(n);return {"ok":True}
async def run_due():
 now=datetime.now(ZoneInfo(TZ));today=now.date().isoformat()
 for s in load():
  if not s.get("enabled") or s.get("last_run_date")==today:continue
  hh,mm=map(int,s["time"].split(":"))
  if now.hour*60+now.minute < hh*60+mm:continue
  try:
   result=await orchestrate(ChatIn(message=s["prompt"]))
   a=load();target=next((x for x in a if x["id"]==s["id"]),None)
   if target:target["last_run_date"]=today;save(a)
   event("schedule_run",{"id":s["id"],"name":s["name"],"answer":result["answer"][:2000]})
  except Exception as e:event("schedule_error",{"id":s["id"],"error":str(e)[:500]})
def scheduler_loop():
 import asyncio
 while True:
  try:asyncio.run(run_due())
  except Exception:pass
  time.sleep(30)
def start_scheduler():
 threading.Thread(target=scheduler_loop,daemon=True,name="jarvis-scheduler").start()
