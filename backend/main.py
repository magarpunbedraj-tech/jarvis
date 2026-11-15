from __future__ import annotations
import os, json, uuid, time, asyncio
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
load_dotenv()
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/"data"; DATA.mkdir(exist_ok=True)
TASKS_FILE=DATA/"tasks.json"; EVENTS_FILE=DATA/"events.jsonl"
app=FastAPI(title="Jarvis AI Agency",version="0.4.0")
app.mount("/static",StaticFiles(directory=str(ROOT/"web")),name="static")
from .scheduler import router as schedule_router, start_scheduler
app.include_router(schedule_router)
@app.on_event("startup")
def startup(): start_scheduler()

AGENTS={
 "manager":{"name":"Agency Manager","role":"Plan tasks, delegate, coordinate and synthesize verified results."},
 "research":{"name":"Research Agent","role":"Research, comparisons, evidence and uncertainty."},
 "coder":{"name":"Coding Agent","role":"Software design, coding, debugging and tests."},
 "browser":{"name":"Browser Agent","role":"Web research and browser workflow analysis; don't claim browser actions ran."},
 "business":{"name":"Business Agent","role":"Business strategy, marketing, operations and revenue."},
 "computer":{"name":"Computer Agent","role":"Windows workflows; don't claim actions ran without local worker."},
 "qa":{"name":"QA Agent","role":"Review outputs, challenge assumptions and identify gaps."},
 "memory":{"name":"Memory Agent","role":"Summarize project context, decisions and task notes."},
 "voice":{"name":"Voice Agent","role":"Voice UX, speech and transcription workflows."}
}
class ChatIn(BaseModel):
 message:str
 agent:str="manager"
 task_id:str|None=None
class TaskIn(BaseModel):
 title:str
 description:str=""
 agent:str="manager"
 priority:str="normal"
class AgentMessage(BaseModel):
 from_agent:str
 to_agent:str
 content:str
 task_id:str|None=None
class WorkerAction(BaseModel):
 action:str
 target:str=""
 selector:str=""
 content:str=""
 approved:bool=False
 x:int|None=None
 y:int|None=None
 amount:int=0
 keys:list[str]=[]


class ComputerInspectIn(BaseModel):
 image_base64:str
 question:str="Describe the current screen and identify visible controls, status, and likely next safe action."
class ComputerStepIn(BaseModel):
 action:WorkerAction
 inspect_after:bool=True
 approved:bool=False

async def vision_call(image_base64,question):
 # Prefer Gemini's native multimodal API; then OpenAI-compatible vision providers.
 key=os.getenv("GEMINI_API_KEY","");model=os.getenv("VISION_MODEL",os.getenv("GEMINI_MODEL","gemini-2.5-flash"))
 if key:
  async with httpx.AsyncClient(timeout=90) as c:
   url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
   r=await c.post(url,json={"contents":[{"parts":[{"text":question},{"inline_data":{"mime_type":"image/png","data":image_base64}}]}],"generationConfig":{"temperature":0.2}})
   r.raise_for_status();return r.json()["candidates"][0]["content"]["parts"][0]["text"],model
 for p in providers():
  if p.get("native"):continue
  async with httpx.AsyncClient(timeout=90) as c:
   r=await c.post(p["base"]+"/chat/completions",headers={"Authorization":"Bearer "+p["key"]},json={"model":os.getenv("VISION_MODEL",p["model"]),"messages":[{"role":"user","content":[{"type":"text","text":question},{"type":"image_url","image_url":{"url":"data:image/png;base64,"+image_base64}}]}],"temperature":0.2})
   r.raise_for_status();return r.json()["choices"][0]["message"]["content"],p["model"]
 raise HTTPException(503,"Vision requires GEMINI_API_KEY or an OpenAI-compatible vision provider in .env")
@app.post("/api/computer/inspect")
async def computer_inspect(body:ComputerInspectIn):
 import base64
 if len(body.image_base64)>12_000_000:raise HTTPException(413,"Screenshot payload too large")
 try:base64.b64decode(body.image_base64,validate=True)
 except Exception:raise HTTPException(400,"image_base64 must be valid base64")
 try:
  answer,model=await vision_call(body.image_base64,body.question[:3000])
  event("computer_screen_inspected",{"model":model,"question":body.question[:250],"answer":answer[:1200]})
  return {"ok":True,"model":model,"analysis":answer}
 except HTTPException:raise
 except Exception as e:raise HTTPException(502,"Vision analysis failed: "+str(e)[:300])
@app.post("/api/computer/step")
async def computer_step(body:ComputerStepIn):
 if not body.approved:raise HTTPException(403,"Human approval required for action")
 # Execute one explicitly approved action, then capture fresh screen for verification.
 body.action.approved=True
 result=await worker_action(body.action)
 screen=None
 if body.inspect_after:
  try:screen=await worker_action(WorkerAction(action="desktop_screenshot",approved=True))
  except Exception as e:screen={"ok":False,"error":str(e)[:250]}
 event("computer_step",{"action":body.action.action,"result":result,"screenshot_captured":bool(screen and screen.get("ok"))})
 return {"ok":True,"action_result":result,"screenshot":screen}

class ComputerPlanIn(BaseModel):
 goal:str
class ComputerExecuteIn(BaseModel):
 actions:list[WorkerAction]
 approved:bool=False

def read_tasks():
 try:return json.loads(TASKS_FILE.read_text(encoding="utf8"))
 except:return []
def write_tasks(x):TASKS_FILE.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding="utf8")
def event(kind,payload):
 row={"id":str(uuid.uuid4()),"time":time.time(),"kind":kind,**payload}
 with EVENTS_FILE.open("a",encoding="utf8") as f:f.write(json.dumps(row,ensure_ascii=False)+"\n")
 return row
def events(limit=150):
 if not EVENTS_FILE.exists():return []
 out=[]
 for line in EVENTS_FILE.read_text(encoding="utf8").splitlines()[-limit:]:
  try:out.append(json.loads(line))
  except:pass
 return out

def providers():
 p=[]
 for name,base,key,model in [
  ("primary",os.getenv("AI_BASE_URL",""),os.getenv("AI_API_KEY",""),os.getenv("AI_MODEL","")),
  ("groq",os.getenv("GROQ_BASE_URL","https://api.groq.com/openai/v1"),os.getenv("GROQ_API_KEY",""),os.getenv("GROQ_MODEL","")),
  ("openrouter",os.getenv("OPENROUTER_BASE_URL","https://openrouter.ai/api/v1"),os.getenv("OPENROUTER_API_KEY",""),os.getenv("OPENROUTER_MODEL",""))]:
  if base and key and model:p.append({"name":name,"base":base.rstrip("/"),"key":key,"model":model})
 if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_MODEL"):
  p.append({"name":"gemini","key":os.getenv("GEMINI_API_KEY"),"model":os.getenv("GEMINI_MODEL"),"native":True})
 return p
async def call_provider(p,messages):
 async with httpx.AsyncClient(timeout=180) as client:
  if p.get("native"):
   prompt="\n\n".join(m["role"].upper()+": "+m["content"] for m in messages)
   url=f"https://generativelanguage.googleapis.com/v1beta/models/{p['model']}:generateContent?key={p['key']}"
   r=await client.post(url,json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.3}})
   r.raise_for_status();return r.json()["candidates"][0]["content"]["parts"][0]["text"]
  r=await client.post(p["base"]+"/chat/completions",headers={"Authorization":"Bearer "+p["key"]},json={"model":p["model"],"messages":messages,"temperature":0.3,"stream":False})
  r.raise_for_status();return r.json()["choices"][0]["message"]["content"]
async def llm(messages):
 errors=[]
 for p in providers():
  try:
   answer=await call_provider(p,messages);event("provider_used",{"provider":p["name"],"model":p["model"]});return answer
  except Exception as e:
   errors.append(p["name"]+": "+str(e)[:200]);event("provider_failed",{"provider":p["name"],"error":str(e)[:250]})
 try:
  async with httpx.AsyncClient(timeout=180) as c:
   r=await c.post(os.getenv("OLLAMA_BASE_URL","http://localhost:11434").rstrip()+"/v1/chat/completions",json={"model":os.getenv("OLLAMA_MODEL","qwen2.5:7b"),"messages":messages})
   r.raise_for_status();return r.json()["choices"][0]["message"]["content"]
 except Exception as e:errors.append("ollama: "+str(e)[:160])
 raise RuntimeError("No AI provider succeeded. Configure a free API key in .env. "+" | ".join(errors))
async def agent_run(agent,prompt,task_id=None,shared_context=""):
 info=AGENTS.get(agent,AGENTS["manager"])
 event("agent_started",{"agent":agent,"task_id":task_id,"prompt":prompt[:500]})
 system=f"You are {info['name']}. Role: {info['role']}\nBe specific and honest. Never claim an external action ran unless verified."
 try:answer=await llm([{"role":"system","content":system},{"role":"user","content":"Task: "+prompt+"\nShared agency context/peer messages: "+shared_context}])
 except Exception as e:answer="AI provider error: "+str(e)
 event("agent_completed",{"agent":agent,"task_id":task_id,"result":answer[:2200]})
 return answer
@app.get("/",response_class=HTMLResponse)
async def home():return (ROOT/"web"/"index.html").read_text(encoding="utf8")
@app.get("/api/health")
async def health():return {"ok":True,"app":"Jarvis AI Agency","agents":list(AGENTS),"providers_configured":len(providers())}
@app.get("/api/agents")
async def agents():return AGENTS
@app.get("/api/providers")
async def provider_status():return {"configured":[{"name":p["name"],"model":p["model"]} for p in providers()],"fallback":"Ollama"}
@app.get("/api/tasks")
async def tasks():return read_tasks()
@app.post("/api/tasks")
async def add_task(body:TaskIn):
 t={"id":str(uuid.uuid4())[:8],"title":body.title,"description":body.description,"agent":body.agent,"priority":body.priority,"status":"queued","created":time.time(),"result":""}
 a=read_tasks();a.insert(0,t);write_tasks(a);event("task_created",t);return t
@app.post("/api/tasks/{task_id}/run")
async def run_task(task_id:str):
 a=read_tasks();t=next((x for x in a if x["id"]==task_id),None)
 if not t:raise HTTPException(404,"Task not found")
 t["status"]="running";write_tasks(a)
 try:
  r=await orchestrate(ChatIn(message=t["title"]+"\n"+t["description"],task_id=task_id))
  t["result"]=r["answer"];t["agent_results"]=r["results"];t["status"]="done"
 except Exception as e:t["result"]=str(e);t["status"]="error"
 t["finished"]=time.time();write_tasks(a);return t
@app.post("/api/chat")
async def chat(body:ChatIn):
 if body.agent not in AGENTS:raise HTTPException(400,"Unknown agent")
 if body.agent=="manager":return await orchestrate(body)
 return {"agent":body.agent,"answer":await agent_run(body.agent,body.message,body.task_id)}
@app.post("/api/agent-message")
async def agent_message(body:AgentMessage):
 if body.from_agent not in AGENTS or body.to_agent not in AGENTS:raise HTTPException(400,"Unknown agent")
 return event("agent_message",body.model_dump())
@app.get("/api/events")
async def get_events():return events()
@app.post("/api/worker/action")
async def worker_action(body:WorkerAction):
 if not body.approved:raise HTTPException(403,"Confirm the exact local action before execution")
 token=os.getenv("WORKER_TOKEN","")
 if not token:raise HTTPException(503,"WORKER_TOKEN is not configured in .env")
 payload={**body.model_dump(),"token":token}
 try:
  async with httpx.AsyncClient(timeout=45) as client:
   r=await client.post("http://127.0.0.1:"+os.getenv("WORKER_PORT","8788")+"/action",json=payload)
   if r.status_code>=400:raise HTTPException(r.status_code,r.text[:800])
   return r.json()
 except httpx.RequestError as e:raise HTTPException(503,"Local worker unavailable. Start worker-start.bat. "+str(e)[:200])
@app.post("/api/computer/plan")
async def computer_plan(body:ComputerPlanIn):
 prompt="Create a cautious PC workflow for this goal: "+body.goal+"\\nReturn JSON only: {steps:[{action:launch_app|desktop_hotkey|desktop_type|desktop_scroll|browser_navigate|browser_fill|browser_click,target:string,keys:[...],content:string,selector:string,amount:int}]}\\nOnly propose reversible steps. Never propose payments, purchases, deletion, account changes, sending messages, or entering passwords/OTP. Use exact Start Menu app names if known. Do not claim actions executed."
 raw=await llm([{"role":"system","content":"Windows automation planner. JSON only."},{"role":"user","content":prompt}])
 try:
  obj=json.loads(raw[raw.find("{"):raw.rfind("}")+1])
  allowed={"launch_app","desktop_hotkey","desktop_type","desktop_scroll","browser_navigate","browser_fill","browser_click","desktop_click"}
  steps=obj.get("steps",[])
  if not isinstance(steps,list):raise ValueError("steps must be a list")
  clean=[]
  for step in steps[:12]:
   if not isinstance(step,dict) or step.get("action") not in allowed:continue
   clean.append({k:step.get(k) for k in ("action","target","selector","content","keys","amount") if k in step})
  return {"goal":body.goal,"steps":clean,"status":"proposal_only"}
 except Exception as e:raise HTTPException(502,"Could not parse computer plan: "+str(e)[:250])
@app.post("/api/computer/execute")
async def computer_execute(body:ComputerExecuteIn):
 if not body.approved:raise HTTPException(403,"Human approval required for entire PC plan")
 if not body.actions:raise HTTPException(400,"No actions supplied")
 if len(body.actions)>12:raise HTTPException(413,"Maximum 12 actions per plan")
 allowed={"launch_app","desktop_hotkey","desktop_type","desktop_scroll","browser_navigate","browser_fill","browser_click","desktop_click"}
 # Validate the complete plan before executing anything, avoiding partial runs on invalid steps.
 for action in body.actions:
  if action.action not in allowed:raise HTTPException(400,"Action not allowlisted for agent plans: "+action.action)
  if action.action=="desktop_hotkey" and not action.keys:raise HTTPException(400,"Hotkey step requires keys")
  if action.action in {"browser_navigate"} and not action.target.startswith(("http://","https://")):raise HTTPException(400,"Browser URL must start with http(s)")
  if action.action in {"browser_fill","browser_click"} and not action.selector:raise HTTPException(400,"Browser selector is required")
 results=[]
 for action in body.actions:
  action.approved=True
  results.append(await worker_action(action))
 return {"ok":True,"results":results}
@app.get("/api/config")
async def config():return {"provider":"cloud" if providers() else "ollama","model":providers()[0]["model"] if providers() else os.getenv("OLLAMA_MODEL","qwen2.5:7b"),"desktop_control":bool(os.getenv("WORKER_TOKEN")),"vision_configured":bool(os.getenv("GEMINI_API_KEY") or providers())}
@app.post("/api/orchestrate")
async def orchestrate(body:ChatIn):
 planner="Return JSON only {steps:[{agent:research|coder|browser|business|computer|qa|memory|voice,task:string}]}. Choose 2-5 distinct specialists for goal: "+body.message
 try:
  raw=await llm([{"role":"system","content":"Project manager. Valid JSON only, no markdown."},{"role":"user","content":planner}])
  plan=json.loads(raw[raw.find("{"):raw.rfind("}")+1]);steps=plan.get("steps",[])[:5]
 except Exception as e:
  event("planner_fallback",{"error":str(e)[:250]})
  steps=[{"agent":"research","task":"Analyze requirements and risks: "+body.message},{"agent":"coder","task":"Propose implementation: "+body.message},{"agent":"qa","task":"Review solution and gaps: "+body.message}]
 context="USER GOAL: "+body.message;results=[];seen=set()
 for step in steps:
  agent=step.get("agent","research")
  if agent not in AGENTS or agent=="manager" or agent in seen:continue
  seen.add(agent);task=str(step.get("task",body.message))
  event("agent_handoff",{"from_agent":"manager","to_agent":agent,"task_id":body.task_id,"content":task})
  out=await agent_run(agent,task,body.task_id,context);results.append({"agent":agent,"task":task,"result":out})
  context+="\n\n[AGENCY MESSAGE "+agent+" -> ALL PEERS] "+out
  event("agent_message",{"from_agent":agent,"to_agent":"agency_shared_context","task_id":body.task_id,"content":out})
 final=await agent_run("manager","Evaluate peer outputs, resolve contradictions, state unverified actions, and deliver a useful answer.",body.task_id,context)
 event("orchestration_completed",{"task_id":body.task_id,"agents":[x["agent"] for x in results]})
 return {"plan":steps,"results":results,"answer":final}
