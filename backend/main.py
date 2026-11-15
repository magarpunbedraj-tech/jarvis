from __future__ import annotations
import os, json, asyncio, uuid, time
from typing import Any
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
TASKS_FILE = DATA / "tasks.json"
EVENTS_FILE = DATA / "events.jsonl"
app = FastAPI(title="Jarvis Multi-Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "web")), name="static")

AGENTS = {
 "manager": {"name":"Jarvis Manager","role":"Plan tasks, delegate to specialist agents, synthesize results. Never claim tools ran unless verified."},
 "coder": {"name":"Coding Agent","role":"Software engineering, code review, debugging, tests. Provide actionable patches/code."},
 "browser": {"name":"Browser Agent","role":"Web research and browsing plans. This MVP does not execute browser actions remotely; use the local Playwright worker."},
 "computer": {"name":"Computer Agent","role":"Desktop automation planning. Only execute via local worker with explicit permissions."},
 "research": {"name":"Research Agent","role":"Research, compare evidence, identify uncertainty and sources."},
 "voice": {"name":"Voice Agent","role":"Voice interaction, transcription and speech output planning."},
 "memory": {"name":"Memory Agent","role":"Extract durable project/task context and concise summaries."}
}
class ChatIn(BaseModel):
 message: str
 agent: str = "manager"
 task_id: str | None = None
class TaskIn(BaseModel):
 title: str
 description: str = ""
 agent: str = "manager"
 priority: str = "normal"
class AgentMessage(BaseModel):
 from_agent: str
 to_agent: str
 content: str
 task_id: str | None = None

def read_tasks():
 try: return json.loads(TASKS_FILE.read_text())
 except: return []
def write_tasks(items): TASKS_FILE.write_text(json.dumps(items,indent=2))
def event(kind, payload):
 row={"id":str(uuid.uuid4()),"time":time.time(),"kind":kind,**payload}
 with EVENTS_FILE.open("a",encoding="utf8") as f: f.write(json.dumps(row)+"\n")
 return row
def events(limit=100):
 if not EVENTS_FILE.exists(): return []
 rows=[]
 for line in EVENTS_FILE.read_text().splitlines()[-limit:]:
  try: rows.append(json.loads(line))
  except: pass
 return rows

async def llm(messages):
 cloud=os.getenv("AI_BASE_URL","").strip()
 key=os.getenv("AI_API_KEY","")
 model=os.getenv("AI_MODEL","")
 if cloud and key and model:
  url=cloud.rstrip("/")+"/chat/completions"
  headers={"Authorization":f"Bearer {key}"}
 else:
  base=os.getenv("OLLAMA_BASE_URL","http://localhost:11434").rstrip("/")
  model=os.getenv("OLLAMA_MODEL","qwen2.5:14b")
  url=base+"/v1/chat/completions"; headers={}
 payload={"model":model,"messages":messages,"temperature":0.3,"stream":False}
 async with httpx.AsyncClient(timeout=180) as client:
  r=await client.post(url,headers=headers,json=payload); r.raise_for_status()
  return r.json()["choices"][0]["message"]["content"]

async def agent_run(agent, prompt, task_id=None, shared_context=""):
 info=AGENTS.get(agent,AGENTS["manager"])
 event("agent_started",{"agent":agent,"task_id":task_id,"prompt":prompt[:500]})
 system=f"You are {info['name']}. Specialty: {info['role']}\nCollaborate through shared task context. Be honest about actions; don't claim execution without tools."
 try:
  answer=await llm([{"role":"system","content":system},{"role":"user","content":f"Task: {prompt}\nShared context/messages: {shared_context}"}])
 except Exception as e:
  answer=f"LLM error: {e}. Check Ollama is running/model pulled or configure AI_BASE_URL + API key."
 event("agent_completed",{"agent":agent,"task_id":task_id,"result":answer[:2000]})
 return answer

@app.get("/",response_class=HTMLResponse)
async def home(): return (ROOT/"web"/"index.html").read_text()
@app.get("/api/health")
async def health(): return {"ok":True,"app":"Jarvis Multi-Agent","agents":list(AGENTS)}
@app.get("/api/agents")
async def agents(): return AGENTS
@app.get("/api/tasks")
async def tasks(): return read_tasks()
@app.post("/api/tasks")
async def add_task(body:TaskIn):
 t={"id":str(uuid.uuid4())[:8],"title":body.title,"description":body.description,"agent":body.agent,"priority":body.priority,"status":"queued","created":time.time(),"result":""}
 items=read_tasks();items.insert(0,t);write_tasks(items);event("task_created",t);return t
@app.post("/api/tasks/{task_id}/run")
async def run_task(task_id:str):
 items=read_tasks(); t=next((x for x in items if x["id"]==task_id),None)
 if not t: raise HTTPException(404,"Task not found")
 t["status"]="running";write_tasks(items)
 result=await agent_run(t["agent"],t["title"]+"\n"+t["description"],task_id)
 t["result"]=result;t["status"]="done";t["finished"]=time.time();write_tasks(items)
 return t
@app.post("/api/chat")
async def chat(body:ChatIn):
 if body.agent not in AGENTS: raise HTTPException(400,"Unknown agent")
 # manager can explicitly delegate by asking it to propose handoffs; UI supports direct agent selection
 answer=await agent_run(body.agent,body.message,body.task_id)
 return {"agent":body.agent,"answer":answer}
@app.post("/api/agent-message")
async def agent_message(body:AgentMessage):
 if body.from_agent not in AGENTS or body.to_agent not in AGENTS: raise HTTPException(400,"Unknown agent")
 row=event("agent_message",body.model_dump())
 return row
@app.get("/api/events")
async def get_events(): return events()
@app.get("/api/config")
async def config():
 return {"provider":"cloud" if os.getenv("AI_BASE_URL") and os.getenv("AI_API_KEY") else "ollama","model":os.getenv("AI_MODEL") or os.getenv("OLLAMA_MODEL","qwen2.5:14b"),"desktop_control":os.getenv("ENABLE_DESKTOP_CONTROL","false").lower()=="true"}


@app.post("/api/orchestrate")
async def orchestrate(body:ChatIn):
 plan_prompt='Return JSON only with steps array; each step has agent (coder/browser/computer/research/voice/memory) and task. Select 1-3 specialists. Request: '+body.message
 try:
  raw=await llm([{"role":"system","content":"Careful planner. Do not select computer for sensitive/destructive actions."},{"role":"user","content":plan_prompt}])
  start=raw.find("{"); end=raw.rfind("}")+1; plan=json.loads(raw[start:end]); steps=plan.get("steps",[])[:3]
 except Exception:
  steps=[{"agent":"research","task":body.message},{"agent":"coder","task":"Give implementation or actionable solution for: "+body.message}]
 context="User goal: "+body.message; results=[]
 for step in steps:
  agent=step.get("agent","research")
  if agent not in AGENTS or agent=="manager": continue
  task=step.get("task",body.message)
  event("agent_handoff",{"from_agent":"manager","to_agent":agent,"task_id":body.task_id,"content":task})
  out=await agent_run(agent,task,body.task_id,context)
  results.append({"agent":agent,"task":task,"result":out})
  context+="\n\n"+agent+" result: "+out
  event("agent_message",{"from_agent":agent,"to_agent":"manager","task_id":body.task_id,"content":out})
 final=await agent_run("manager","Synthesize specialist results into one verified answer.",body.task_id,context)
 return {"plan":steps,"results":results,"answer":final}
