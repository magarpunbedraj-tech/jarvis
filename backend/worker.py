"""Local Windows execution worker for Jarvis. Runs only allowlisted, user-approved tools."""
from __future__ import annotations
import os, subprocess, webbrowser, time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()
app=FastAPI(title="Jarvis Local Worker",version="0.1.0")
TOKEN=os.getenv("WORKER_TOKEN","")
HOST=os.getenv("WORKER_HOST","127.0.0.1")
PORT=int(os.getenv("WORKER_PORT","8788"))
ROOT=Path(__file__).resolve().parent.parent

def auth(token:str):
 if not TOKEN or token!=TOKEN: raise HTTPException(401,"Invalid worker token")

class Action(BaseModel):
 token:str
 action:Literal["open_url","open_folder","open_app","write_file","read_file","list_folder","browse_page"]
 target:str=""
 content:str=""
 approved:bool=False

@app.get("/health")
async def health(): return {"ok":True,"worker":"local","host":HOST,"port":PORT,"approval_required":True}

@app.post("/action")
async def action(a:Action):
 auth(a.token)
 if not a.approved: raise HTTPException(403,"Human approval required. Set approved=true only after explicit user confirmation.")
 if a.action=="open_url":
  if not a.target.startswith(("https://","http://")): raise HTTPException(400,"Only http(s) URLs allowed")
  webbrowser.open(a.target);return {"ok":True,"action":a.action,"target":a.target}
 if a.action=="open_app":
  # Restrict to known apps; never pass arbitrary shell commands.
  apps={"notepad":"notepad.exe","calculator":"calc.exe","paint":"mspaint.exe"}
  if a.target.lower() not in apps: raise HTTPException(400,"Allowed apps: "+", ".join(apps))
  subprocess.Popen([apps[a.target.lower()]],shell=False);return {"ok":True,"app":a.target}
 if a.action in ("read_file","write_file","list_folder","open_folder"):
  p=(ROOT/a.target).resolve()
  if ROOT not in p.parents and p!=ROOT: raise HTTPException(400,"Path must remain inside project folder")
  if a.action=="read_file":
   if not p.is_file():raise HTTPException(404,"File not found")
   if p.stat().st_size>1_000_000:raise HTTPException(413,"File >1MB")
   return {"ok":True,"content":p.read_text(encoding="utf8",errors="replace")}
  if a.action=="write_file":
   if len(a.content)>200_000:raise HTTPException(413,"Content >200KB")
   p.parent.mkdir(parents=True,exist_ok=True);p.write_text(a.content,encoding="utf8");return {"ok":True,"path":str(p.relative_to(ROOT))}
  if a.action=="list_folder":
   if not p.is_dir():raise HTTPException(404,"Folder not found")
   return {"ok":True,"items":[{"name":x.name,"directory":x.is_dir()} for x in list(p.iterdir())[:200]]}
  if a.action=="open_folder":
   if not p.is_dir():raise HTTPException(404,"Folder not found")
   os.startfile(str(p));return {"ok":True,"path":str(p)}
 raise HTTPException(400,"Unsupported action")

if __name__=="__main__":
 import uvicorn
 uvicorn.run(app,host=HOST,port=PORT)
