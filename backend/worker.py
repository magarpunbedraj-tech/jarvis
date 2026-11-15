"""Jarvis local Windows worker. Allowlisted actions require explicit human approval."""
from __future__ import annotations
import os, subprocess, webbrowser
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()
app=FastAPI(title="Jarvis Local Worker",version="0.3.0")
TOKEN=os.getenv("WORKER_TOKEN","")
HOST=os.getenv("WORKER_HOST","127.0.0.1")
PORT=int(os.getenv("WORKER_PORT","8788"))
ROOT=Path(__file__).resolve().parent.parent
_browser=None
_page=None
_pw=None

def auth(token:str):
 if not TOKEN or token!=TOKEN: raise HTTPException(401,"Invalid worker token")
def approved(a):
 if not a.approved: raise HTTPException(403,"Human approval required; approve the exact action in Jarvis first.")
def safe_url(url):
 if not url.startswith(("https://","http://")): raise HTTPException(400,"Only http(s) URLs allowed")
class Action(BaseModel):
 token:str
 action:Literal["open_url","open_folder","open_app","write_file","read_file","list_folder","browse_page","browser_start","browser_navigate","browser_fill","browser_click","browser_text","browser_close","list_apps","launch_app","desktop_screenshot","desktop_click","desktop_type","desktop_hotkey","desktop_scroll"]
 target:str=""
 selector:str=""
 content:str=""
 approved:bool=False
 x:int|None=None
 y:int|None=None
 amount:int=0
 keys:list[str]=[]

@app.get("/health")
async def health():return {"ok":True,"worker":"local","version":"0.2.0","host":HOST,"port":PORT,"approval_required":True,"browser_open":_page is not None}

@app.post("/action")
async def action(a:Action):
 global _browser,_page,_pw
 auth(a.token);approved(a)
 if a.action=="list_apps":
  folders=[Path(os.getenv("APPDATA",""))/"Microsoft/Windows/Start Menu/Programs",Path(os.getenv("PROGRAMDATA","C:/ProgramData"))/"Microsoft/Windows/Start Menu/Programs"]
  apps=[]
  for folder in folders:
   if folder.exists():
    apps.extend({"name":p.stem,"path":str(p)} for p in folder.rglob("*.lnk"))
  return {"ok":True,"apps":sorted(apps,key=lambda x:x["name"].lower())[:400]}
 if a.action=="launch_app":
  folders=[Path(os.getenv("APPDATA",""))/"Microsoft/Windows/Start Menu/Programs",Path(os.getenv("PROGRAMDATA","C:/ProgramData"))/"Microsoft/Windows/Start Menu/Programs"]
  match=next((p for folder in folders if folder.exists() for p in folder.rglob("*.lnk") if p.stem.lower()==a.target.lower()),None)
  if not match:raise HTTPException(404,"App shortcut not found; list apps first")
  os.startfile(str(match));return {"ok":True,"launched":match.stem}
 if a.action.startswith("desktop_"):
  import pyautogui as pg
  if a.action=="desktop_screenshot":
   import base64,io
   buf=io.BytesIO();pg.screenshot().save(buf,format="PNG")
   return {"ok":True,"image_base64":base64.b64encode(buf.getvalue()).decode(),"width":pg.size().width,"height":pg.size().height}
  if a.action=="desktop_click":
   if a.x is None or a.y is None or not (0<=a.x<pg.size().width and 0<=a.y<pg.size().height):raise HTTPException(400,"Valid x/y screen coordinates required")
   pg.click(a.x,a.y);return {"ok":True,"clicked":[a.x,a.y]}
  if a.action=="desktop_type":
   if len(a.content)>5000:raise HTTPException(413,"Text max 5000")
   # Clipboard paste supports Nepali/Unicode; pyautogui.write is ASCII-only.
   import pyperclip
   previous=pyperclip.paste()
   try:
    pyperclip.copy(a.content);pg.hotkey("ctrl","v")
   finally:pyperclip.copy(previous)
   return {"ok":True,"typed":len(a.content),"method":"clipboard_paste"}
  if a.action=="desktop_hotkey":
   allowed={"ctrl","alt","shift","win","enter","tab","esc","space","backspace","delete","up","down","left","right","home","end","pageup","pagedown","f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12","a","c","v","x","z","y","s","w","t","r","l","d"}
   if not a.keys or any(k.lower() not in allowed for k in a.keys):raise HTTPException(400,"Hotkey not allowlisted")
   pg.hotkey(*[k.lower() for k in a.keys]);return {"ok":True,"keys":a.keys}
  if a.action=="desktop_scroll":pg.scroll(max(-20,min(20,a.amount)));return {"ok":True,"scroll":a.amount}
 if a.action=="browse_page":
  safe_url(a.target)
  try:
   from playwright.async_api import async_playwright
   async with async_playwright() as pw:
    browser=await pw.chromium.launch(headless=True);page=await browser.new_page()
    await page.goto(a.target,wait_until="domcontentloaded",timeout=30000)
    result={"ok":True,"url":a.target,"title":await page.title(),"text":(await page.locator("body").inner_text())[:12000]}
    await browser.close();return result
  except Exception as e:raise HTTPException(500,"Browser read failed: "+str(e)[:300])
 if a.action=="browser_start":
  if _page:return {"ok":True,"message":"Browser session already open"}
  try:
   from playwright.async_api import async_playwright
   _pw=await async_playwright().start();_browser=await _pw.chromium.launch(headless=False);_page=await _browser.new_page()
   await _page.goto("about:blank");return {"ok":True,"message":"Visible browser session opened"}
  except Exception as e:raise HTTPException(500,"Browser launch failed. Run playwright install chromium. "+str(e)[:250])
 if a.action=="browser_close":
  if _browser:await _browser.close();_browser=None;_page=None
  if _pw:await _pw.stop();_pw=None
  return {"ok":True,"message":"Browser closed"}
 if a.action=="browser_navigate":
  if not _page:raise HTTPException(409,"Start browser session first")
  safe_url(a.target);await _page.goto(a.target,wait_until="domcontentloaded",timeout=30000)
  return {"ok":True,"url":_page.url,"title":await _page.title()}
 if a.action in ("browser_fill","browser_click","browser_text"):
  if not _page:raise HTTPException(409,"Start browser session first")
  if not a.selector:raise HTTPException(400,"A CSS selector is required")
  loc=_page.locator(a.selector).first
  if a.action=="browser_fill":
   if len(a.content)>10000:raise HTTPException(413,"Text >10KB")
   await loc.fill(a.content);return {"ok":True,"action":"filled","selector":a.selector}
  if a.action=="browser_click":
   await loc.click(timeout=15000);return {"ok":True,"action":"clicked","selector":a.selector}
  return {"ok":True,"text":(await loc.inner_text())[:8000]}
 if a.action=="open_url":
  safe_url(a.target);webbrowser.open(a.target);return {"ok":True,"target":a.target}
 if a.action=="open_app":
  apps={"notepad":"notepad.exe","calculator":"calc.exe","paint":"mspaint.exe"}
  if a.target.lower() not in apps:raise HTTPException(400,"Allowed apps: "+", ".join(apps))
  subprocess.Popen([apps[a.target.lower()]],shell=False);return {"ok":True,"app":a.target}
 if a.action in ("read_file","write_file","list_folder","open_folder"):
  p=(ROOT/a.target).resolve()
  if ROOT not in p.parents and p!=ROOT:raise HTTPException(400,"Path must remain inside project folder")
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
