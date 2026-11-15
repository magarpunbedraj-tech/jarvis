from __future__ import annotations
import os, json, asyncio, uuid, time
from pathlib import Path
from typing import Any
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field\nfrom .scheduler import router as schedule_router, start_scheduler

load_dotenv()
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/"data"; DATA.mkdir(exist_ok=True)
TASKS_FILE=DATA/"tasks.json"; EVENTS_FILE=DATA/"events.jsonl"
app=FastAPI(title="Jarvis AI Agency",version="0.2.0")
app.mount("/static",StaticFiles(directory=str(ROOT/"web")),name="static")\napp.include_router(schedule_router)\n@app.on_event("startup")\ndef startup(): start_scheduler()

AGENTS={
 "manager":{"name":"Agency Manager","role":"Break goals into tasks, choose specialists, coordinate, challenge weak results and synthesize."},
 "research":{"name":"Research Agent","role":"Research, evidence, comparisons, assumptions and source-aware analysis."},
 "coder":{"name":"Coding Agent","role":"Software architecture, code, debugging, tests and implementation."},
 "browser":{"name":"Browser Agent","role":"Web research plans, website analysis and browser workflow design; no browser execution in this MVP."},
 "business":{"name":"Business Agent","role":"Business strategy, operations, marketing, product and revenue plans."},
 "computer":{"name":"Computer Agent","role":"Windows workflow planning; never claim desktop actions actually executed."},
 "qa":{"name":"QA Agent","role":"Critique, fact-check, test planning, risk analysis and acceptance criteria."},
 "memory":{"name":"Memory Agent","role":"Summarize useful task context, decisions and durable project notes."},
 "voice":{"name":"Voice Agent","role":"Voice UX, transcription and speech workflow design."}
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

def read_tasks():
 try:return json.loads(TASKS_FILE.read_text())
 except:return []
def write_tasks(x):TASKS_FILE.write_text(json.dumps(x,indent=2,ensure_ascii=False))
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
 # OpenAI-compatible providers, ordered by preference; each is optional.
 for name,base,key,model in [
  ("primary",os.getenv("AI_BASE_URL",""),os.getenv("AI_API_KEY",""),os.getenv("AI_MODEL","")),
  ("groq",os.getenv("GROQ_BASE_URL","https://api.groq.com/openai/v1"),os.getenv("GROQ_API_KEY",""),os.getenv("GROQ_MODEL","")),
  ("openrouter",os.getenv("OPENROUTER_BASE_URL","https://openrouter.ai/api/v1"),os.getenv("OPENROUTER_API_KEY",""),os.getenv("OPENROUTER_MODEL","")),
 ]:
  if base and key and model:p.append({"name":name,"base":base.rstrip("/"),"key":key,"model":model})
 # Gemini native API, optional and tried after compatible providers.
 if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_MODEL"):
  p.append({"name":"gemini","key":os.getenv("GEMINI_API_KEY"),"model":os.getenv("GEMINI_MODEL"),"native":True})
 return p

async def call_provider(p,messages):
 async with httpx.AsyncClient(timeout=180) as client:
  if p.get("native"):
   prompt="\n\n".join(("SYSTEM: "+m["content"] if m["role"]=="system" else m["role"].upper()+": "+m["content"]) for m in messages)
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
   errors.append(p["name"]+": "+str(e)[:220]);event("provider_failed",{"provider":p["name"],"error":str(e)[:300]})
 # Ollama is optional fallback
 try:
  base=os.getenv("OLLAMA_BASE_URL","http://localhost:11434").rstrip("/")
  model=os.getenv("OLLAMA_MODEL","qwen2.5:7b")
  async with httpx.AsyncClient(timeout=180) as c:
   r=await c.post(base+"/v1/chat/completions",json={"model":model,"messages":messages,"temperature":0.3})
   r.raise_for_status();return r.json()["choices"][0]["message"]["content"]
 except Exception as e:errors.append("ollama: "+str(e)[:180])
 raise RuntimeError("No AI provider succeeded. Configure one free API key in .env. "+" | ".join(errors))

async def agent_run(agent,prompt,task_id=None,shared_context=""):
 info=AGENTS.get(agent,AGENTS["manager"])
 event("agent_started",{"agent":agent,"task_id":task_id,"prompt":prompt[:500]})
 system=f"You are {info['name']}. Role: {info['role']}\nYou are one member of a multi-agent agency. Be concise, specific, transparent about uncertainty. Never claim an external action was executed unless a tool verified it."
 try:answer=await llm([{"role":"system","content":system},{"role":"user","content":"Task: "+prompt+"\nShared agency context and peer messages: "+shared_context}])
 except Exception as e:answer="AI provider error: "+str(e)
 event("agent_completed",{"agent":agent,"task_id":task_id,"result":answer[:2500]})
 return answer

@app.get("/",response_class=HTMLResponse)
async def home():return (ROOT/"web"/"index.html").read_text()
@app.get("/api/health")
async def health():return {"ok":True,"app":"Jarvis AI Agency","agents":list(AGENTS),"providers_configured":len(providers())}
@app.get("/api/agents")
async def agents():return AGENTS
@app.get("/api/providers")
async def provider_status():
 return {"configured":[{"name":p["name"],"model":p["model"]} for p in providers()],"fallback":"Ollama"}
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
  result=await orchestrate(ChatIn(message=t["title"]+"\n"+t["description"],task_id=task_id))
  t["result"]=result["answer"];t["agent_results"]=result["results"];t["status"]="done"
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
@app.get("/api/config")
async def config():
 return {"provider":"cloud" if providers() else "ollama","model":providers()[0]["model"] if providers() else os.getenv("OLLAMA_MODEL","qwen2.5:7b"),"desktop_control":False}

@app.post("/api/orchestrate")
async def orchestrate(body:ChatIn):
 # Manager creates a JSON delegation plan; safe allowlist and max 5 agents.
 planner="Create a task plan as JSON only: {steps:[{agent:research|coder|browser|business|computer|qa|memory|voice,task:string}]}. Choose 2-5 useful distinct specialists. Do not include manager. Goal: "+body.message
 try:
  raw=await llm([{"role":"system","content":"You are a project manager. Return valid JSON only, no markdown."},{"role":"user","content":planner}])
  plan=json.loads(raw[raw.find("{"):raw.rfind("}")+1]);steps=plan.get("steps",[])[:5]
 except Exception as e:
  event("planner_fallback",{"error":str(e)[:300]})
  steps=[{"agent":"research","task":"Analyze requirements and risks for: "+body.message},{"agent":"coder","task":"Propose concrete solution/implementation for: "+body.message},{"agent":"qa","task":"Review likely solution, identify gaps and safe next steps for: "+body.message}]
 context="USER GOAL: "+body.message;results=[];seen=set()
 for step in steps:
  agent=step.get("agent","research")
  if agent not in AGENTS or agent=="manager" or agent in seen:continue
  seen.add(agent);task=str(step.get("task",body.message))
  event("agent_handoff",{"from_agent":"manager","to_agent":agent,"task_id":body.task_id,"content":task})
  out=await agent_run(agent,task,body.task_id,context)
  results.append({"agent":agent,"task":task,"result":out})
  # Each specialist's output is shared with the next agent (peer-to-peer via manager bus).
  context+="\n\n[AGENCY MESSAGE "+agent+" -> ALL PEERS] "+out
  event("agent_message",{"from_agent":agent,"to_agent":"agency_shared_context","task_id":body.task_id,"content":out})
 final=await agent_run("manager","Evaluate peer outputs, resolve contradictions, state remaining unverified actions, and deliver one useful final response.",body.task_id,context)
 event("orchestration_completed",{"task_id":body.task_id,"agents":[x["agent"] for x in results]})
 return {"plan":steps,"results":results,"answer":final}
