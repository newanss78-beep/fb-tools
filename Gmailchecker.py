#!/usr/bin/env python3
"""
Gmail IMAP Login Checker — Web + CLI
=====================================
Railway-ready (Web UI DEFAULT).

Local test:
    python Gmailchecker.py --web              # http://localhost:5000
    python Gmailchecker.py accounts.txt       # CLI mode
    PORT=8080 python Gmailchecker.py          # env PORT দিয়ে web mode

Railway:
    Start Command: python Gmailchecker.py --web
"""
import imaplib, re, sys, csv, io, os, time, uuid, threading, argparse, functools
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from flask import Flask, request, jsonify, Response

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
IMAP_TIMEOUT = 15
DEFAULT_WORKERS = int(os.environ.get("WORKERS", "5"))
MAX_WORKERS = 20
MAX_ACCOUNTS_PER_JOB = 500
JOB_TTL = 1800                 # 30 min
RATE_WINDOW = 60               # seconds
RATE_MAX = 10                  # requests per IP per window
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


# ═══════════════════════════════════════════════════════════
# INPUT PARSING
# ═══════════════════════════════════════════════════════════
def parse_line(line):
    """`email|app_password` (বা tab/semicolon/colon) → (email, password) | None"""
    line = (line or "").strip().lstrip("\ufeff")
    if not line or line.startswith("#"):
        return None
    if "|" in line:
        em, pw = line.split("|", 1)
    elif "\t" in line:
        em, pw = line.split("\t", 1)
    elif ";" in line:
        em, pw = line.split(";", 1)
    elif ":" in line and "@" in line and line.index(":") > line.index("@"):
        em, pw = line.split(":", 1)
    else:
        return None
    em, pw = em.strip(), pw.strip()
    if not em or not pw or not EMAIL_RE.match(em):
        return None
    return em, pw


# ═══════════════════════════════════════════════════════════
# CORE IMAP CHECK
# ═══════════════════════════════════════════════════════════
def check_gmail(email, password):
    """Real Gmail IMAP login. Returns dict with status + message."""
    pw_clean = re.sub(r"\s+", "", password)
    M = None
    try:
        try:
            M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=IMAP_TIMEOUT)
        except TypeError:
            M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        M.login(email, pw_clean)
        return {"status": "OK", "message": ""}
    except imaplib.IMAP4.error as e:
        err = str(e).lower()
        if "disabled" in err and "imap" in err:
            return {"status": "IMAP_DISABLED", "message": "IMAP disabled in Gmail settings"}
        if "blocked" in err or "too many" in err:
            return {"status": "BLOCKED", "message": "IP or account blocked by Google"}
        if any(k in err for k in ("invalid credentials", "authentication failed",
                                   "login failed", "username and password not accepted",
                                   "invalid username or password")):
            return {"status": "FAILED", "message": "Invalid credentials / wrong app password"}
        return {"status": "FAILED", "message": str(e)[:100]}
    except (OSError, TimeoutError, ConnectionError) as e:
        return {"status": "NETWORK_ERROR", "message": f"{type(e).__name__}: {str(e)[:80]}"}
    except Exception as e:
        return {"status": "NETWORK_ERROR", "message": f"{type(e).__name__}: {str(e)[:80]}"}
    finally:
        try:
            if M is not None:
                M.logout()
        except Exception:
            pass


def run_batch(accounts, workers=DEFAULT_WORKERS, on_progress=None):
    """Check all (email, password) pairs in parallel. Returns ordered results."""
    seen, indexed = {}, []
    for i, (em, pw) in enumerate(accounts):
        key = (em.lower(), pw)
        if key in seen:
            indexed.append((i, em, pw, seen[key]))
        else:
            seen[key] = i
            indexed.append((i, em, pw, None))

    results = [None] * len(accounts)
    done_count = [0]
    lock = threading.Lock()

    def _do(idx, em, pw, dup_of):
        if dup_of is not None:
            res = {"status": "DUPLICATE", "message": f"Duplicate of line {dup_of + 1}"}
        else:
            res = check_gmail(em, pw)
        res.update({"index": idx, "email": em, "password": pw})
        with lock:
            results[idx] = res
            done_count[0] += 1
            if on_progress:
                try:
                    on_progress(done_count[0], len(accounts), res)
                except Exception:
                    pass

    workers = max(1, min(int(workers), MAX_WORKERS))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_do, idx, em, pw, dup)
                   for idx, em, pw, dup in indexed]
        for _ in as_completed(futures):
            pass
    return results


# ═══════════════════════════════════════════════════════════
# FLASK APP (module-level → Railway/gunicorn friendly)
# ═══════════════════════════════════════════════════════════
app = Flask(__name__)

_jobs = {}
_jobs_lock = threading.Lock()
_ip_hits = defaultdict(deque)
_ip_lock = threading.Lock()


def _check_rate(ip):
    now = time.time()
    with _ip_lock:
        dq = _ip_hits[ip]
        while dq and dq[0] < now - RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_MAX:
            return False
        dq.append(now)
        return True


def _require_auth(f):
    """Optional Basic Auth via env AUTH_USER / AUTH_PASS. না থাকলে auth বন্ধ।"""
    @functools.wraps(f)
    def wrapper(*a, **kw):
        want_u = os.environ.get("AUTH_USER", "").strip()
        want_p = os.environ.get("AUTH_PASS", "").strip()
        if not want_u or not want_p:
            return f(*a, **kw)
        auth = request.authorization
        if not auth or auth.username != want_u or auth.password != want_p:
            return Response("Authentication required", 401,
                            {"WWW-Authenticate": 'Basic realm="Gmail Checker"'})
        return f(*a, **kw)
    return wrapper


def _cleanup_jobs():
    now = time.time()
    with _jobs_lock:
        for j in [k for k, v in list(_jobs.items()) if now - v["started"] > JOB_TTL]:
            _jobs.pop(j, None)


def _create_job(accounts, workers):
    jid = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[jid] = {"id": jid, "total": len(accounts), "done": 0,
                      "results": [None] * len(accounts),
                      "started": time.time(), "finished": False}

    def _worker():
        job = _jobs[jid]

        def _on(done, total, res):
            job["done"] = done
            job["results"][res["index"]] = {
                "line": res["index"] + 1, "email": res["email"],
                "status": res["status"], "message": res["message"],
            }

        try:
            run_batch(accounts, workers=workers, on_progress=_on)
        finally:
            job["finished"] = True

    threading.Thread(target=_worker, daemon=True).start()
    return jid


@app.route("/health")
def health():
    return {"status": "ok", "service": "gmail-checker"}, 200


@app.route("/")
@_require_auth
def index():
    return Response(INDEX_HTML, mimetype="text/html")


@app.route("/api/check", methods=["POST"])
@_require_auth
def api_check():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    if not _check_rate(ip):
        return jsonify({"ok": False, "error": "অনেকবার অনুরোধ — ১ মিনিট পর আবার চেষ্টা করুন"}), 429
    _cleanup_jobs()
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    workers = int(data.get("workers") or DEFAULT_WORKERS)
    if not text:
        return jsonify({"ok": False, "error": "কোনো ডেটা নেই"})
    accounts = [a for a in (parse_line(l) for l in text.splitlines()) if a]
    if not accounts:
        return jsonify({"ok": False, "error": "কোনো সঠিক mail|password লাইন পাওয়া যায়নি"})
    if len(accounts) > MAX_ACCOUNTS_PER_JOB:
        return jsonify({"ok": False, "error": f"প্রতি ব্যাচে সর্বোচ্চ {MAX_ACCOUNTS_PER_JOB}টি"})
    jid = _create_job(accounts, workers)
    return jsonify({"ok": True, "job_id": jid, "total": len(accounts)})


@app.route("/api/status/<jid>")
@_require_auth
def api_status(jid):
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job:
            return jsonify({"ok": False, "error": "Job not found"}), 404
        return jsonify({"ok": True, "total": job["total"], "done": job["done"],
                        "finished": job["finished"],
                        "results": [r for r in job["results"] if r is not None]})


@app.route("/api/export/<jid>")
@_require_auth
def api_export(jid):
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job:
            return "Job not found", 404
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["line", "email", "status", "message"])
        for r in job["results"]:
            if r:
                w.writerow([r["line"], r["email"], r["status"], r["message"]])
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=gmail_check_{jid[:8]}.csv"})


# ═══════════════════════════════════════════════════════════
# WEB UI (embedded HTML)
# ═══════════════════════════════════════════════════════════
INDEX_HTML = r"""<!doctype html>
<html lang="bn"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gmail IMAP Checker</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Bengali",sans-serif;
  background:linear-gradient(160deg,#eef2ff,#f5f3ff);color:#1e293b;min-height:100vh;padding:24px}
.wrap{max-width:1000px;margin:0 auto}
h1{margin:0 0 6px;font-size:24px}
.sub{color:#64748b;font-size:14px;margin-bottom:20px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:20px;
  margin-bottom:16px;box-shadow:0 4px 16px rgba(0,0,0,.04)}
h2{font-size:14px;text-transform:uppercase;color:#64748b;letter-spacing:.5px;margin:0 0 12px}
textarea{width:100%;min-height:180px;padding:14px;border:1px solid #e2e8f0;border-radius:10px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;resize:vertical;outline:none}
textarea:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.12)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:12px}
button{padding:10px 20px;border-radius:10px;border:1px solid #e2e8f0;background:#fff;
  color:#1e293b;font-weight:600;font-size:14px;cursor:pointer;transition:.15s}
button:hover{background:#f8fafc;border-color:#cbd5e1}
button.primary{background:linear-gradient(180deg,#6366f1,#4f46e5);border-color:#6366f1;color:#fff}
button.primary:hover{filter:brightness(1.1)}
button:disabled{opacity:.6;cursor:wait}
.filebox{padding:10px 16px;border:1px dashed #cbd5e1;border-radius:10px;font-size:13px;
  color:#64748b;cursor:pointer}
.filebox:hover{border-color:#6366f1;color:#4f46e5}
input[type=file]{display:none}
.workers{display:flex;align-items:center;gap:8px;font-size:13px;color:#64748b}
input[type=number]{width:70px;padding:6px 8px;border:1px solid #e2e8f0;border-radius:8px;font-size:13px}
.progress{height:8px;background:#e2e8f0;border-radius:99px;overflow:hidden;margin-top:12px}
.progress > div{height:100%;background:linear-gradient(90deg,#6366f1,#8b5cf6);width:0;transition:width .2s}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-top:14px}
.stat{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px;text-align:center}
.stat .n{font-size:20px;font-weight:700}
.stat .l{font-size:11px;color:#64748b;margin-top:2px}
.n.ok{color:#16a34a}.n.bad{color:#dc2626}.n.warn{color:#ca8a04}.n.dup{color:#9333ea}.n.net{color:#0891b2}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #f1f5f9}
th{background:#f8fafc;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#64748b;font-weight:600}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.badge{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;font-weight:700}
.b-OK{background:#dcfce7;color:#166534}
.b-FAILED{background:#fee2e2;color:#991b1b}
.b-DUPLICATE{background:#fef3c7;color:#854d0e}
.b-IMAP_DISABLED{background:#f3e8ff;color:#6b21a8}
.b-BLOCKED{background:#fee2e2;color:#991b1b}
.b-NETWORK_ERROR{background:#cffafe;color:#155e75}
.tblwrap{max-height:520px;overflow:auto;border:1px solid #e2e8f0;border-radius:12px;margin-top:12px}
.foot{text-align:center;color:#94a3b8;font-size:12px;margin-top:20px}
</style></head><body><div class="wrap">
<h1>📧 Gmail IMAP Checker</h1>
<div class="sub">Real IMAP login check — <code>mail|app_password</code> পেস্ট বা আপলোড করুন</div>
<div class="card"><h2>Input</h2>
<textarea id="inp" placeholder="user1@gmail.com|abcd efgh ijkl mnop
user2@gmail.com|password123"></textarea>
<div class="row">
<label class="filebox" for="file">📁 ফাইল আপলোড (.txt)</label>
<input type="file" id="file" accept=".txt,.csv,text/plain">
<div class="workers">⚙️ Workers: <input type="number" id="wk" min="1" max="20" value="5"></div>
<button class="primary" id="go">🚀 চেক করুন</button>
<button id="clear">🗑️ ক্লিয়ার</button>
</div></div>
<div class="card" id="resCard" style="display:none"><h2>Results</h2>
<div class="progress"><div id="bar"></div></div>
<div class="stats" id="stats"></div>
<div class="row">
<button id="csv">⬇️ CSV ডাউনলোড</button>
<span id="statustxt" style="color:#64748b;font-size:13px"></span>
</div>
<div class="tblwrap"><table>
<thead><tr><th style="width:60px">Line</th><th>Email</th><th style="width:160px">Status</th><th>Message</th></tr></thead>
<tbody id="tbody"></tbody></table></div></div>
<div class="foot">Hosted on Railway · Gmail IMAP</div>
</div>
<script>
const $=s=>document.querySelector(s);let currentJob=null,pollTimer=null;
$("#file").onchange=async e=>{const f=e.target.files[0];if(!f)return;
  $("#inp").value=await f.text();e.target.value=""};
$("#clear").onclick=()=>{$("#inp").value="";$("#resCard").style.display="none";
  if(pollTimer)clearInterval(pollTimer);currentJob=null};
$("#go").onclick=async()=>{
  const text=$("#inp").value.trim();if(!text){alert("ডেটা দিন");return}
  $("#go").disabled=true;$("#go").textContent="⏳ চলছে...";
  $("#resCard").style.display="block";$("#tbody").innerHTML="";$("#stats").innerHTML="";
  $("#bar").style.width="0%";
  try{const r=await fetch("/api/check",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({text,workers:parseInt($("#wk").value)||5})});
    const d=await r.json();if(!d.ok){alert(d.error||"Error");resetBtn();return}
    currentJob=d.job_id;$("#statustxt").textContent=`0 / ${d.total} চেক হচ্ছে...`;
    pollTimer=setInterval(poll,500);
  }catch(e){alert("Network error: "+e.message);resetBtn()}};
function resetBtn(){$("#go").disabled=false;$("#go").textContent="🚀 চেক করুন"}
function poll(){if(!currentJob)return;
  fetch(`/api/status/${currentJob}`).then(r=>r.json()).then(d=>{
    if(!d.ok){clearInterval(pollTimer);resetBtn();return}
    render(d);
    if(d.finished){clearInterval(pollTimer);resetBtn();
      $("#statustxt").textContent=`✅ শেষ — ${d.total}টি চেক হয়েছে`}
    else{$("#statustxt").textContent=`${d.done} / ${d.total} চেক হচ্ছে...`}
  }).catch(()=>{})}
function render(d){const pct=d.total?(d.done/d.total*100):0;
  $("#bar").style.width=pct+"%";
  const c={OK:0,FAILED:0,DUPLICATE:0,IMAP_DISABLED:0,BLOCKED:0,NETWORK_ERROR:0};
  d.results.forEach(r=>{if(c[r.status]!==undefined)c[r.status]++});
  $("#stats").innerHTML=`
    <div class="stat"><div class="n ok">${c.OK}</div><div class="l">✅ OK</div></div>
    <div class="stat"><div class="n bad">${c.FAILED}</div><div class="l">❌ Failed</div></div>
    <div class="stat"><div class="n dup">${c.DUPLICATE}</div><div class="l">♻️ Duplicate</div></div>
    <div class="stat"><div class="n warn">${c.IMAP_DISABLED}</div><div class="l">🚫 IMAP Off</div></div>
    <div class="stat"><div class="n bad">${c.BLOCKED}</div><div class="l">🛑 Blocked</div></div>
    <div class="stat"><div class="n net">${c.NETWORK_ERROR}</div><div class="l">📡 Network</div></div>`;
  $("#tbody").innerHTML=d.results.map(r=>`<tr>
    <td class="mono" style="color:#64748b">${r.line}</td>
    <td class="mono">${esc(r.email)}</td>
    <td><span class="badge b-${r.status}">${label(r.status)}</span></td>
    <td style="color:#64748b;font-size:12px">${esc(r.message||"")}</td></tr>`).join("")}
function label(s){return({OK:"✅ OK",FAILED:"❌ Failed",DUPLICATE:"♻️ Duplicate",
  IMAP_DISABLED:"🚫 IMAP Off",BLOCKED:"🛑 Blocked",NETWORK_ERROR:"📡 Network"})[s]||s}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",
  '"':"&quot;","'":"&#39;"}[c]))}
$("#csv").onclick=()=>{if(currentJob)window.location.href=`/api/export/${currentJob}`};
</script></body></html>"""


# ═══════════════════════════════════════════════════════════
# CLI MODE
# ═══════════════════════════════════════════════════════════
COLOR = {"OK": "\033[92m", "FAILED": "\033[91m", "DUPLICATE": "\033[93m",
         "IMAP_DISABLED": "\033[95m", "BLOCKED": "\033[91m", "NETWORK_ERROR": "\033[96m"}
RESET = "\033[0m"


def cli_main(args):
    if args.input == "-" or not args.input:
        print("Reading from stdin (Ctrl+D to finish)...")
        raw = sys.stdin.read()
        source_name = "stdin"
    else:
        p = Path(args.input)
        if not p.exists():
            print(f"❌ File not found: {args.input}", file=sys.stderr)
            return 1
        raw = p.read_text(encoding="utf-8", errors="ignore")
        source_name = p.name

    accounts = [a for a in (parse_line(l) for l in raw.splitlines()) if a]
    if not accounts:
        print("❌ No valid accounts found.", file=sys.stderr)
        return 1

    print(f"📄 {source_name} → {len(accounts)} accounts loaded")
    print(f"⚙️  Checking with {args.workers} workers...\n")

    def _progress(done, total, _):
        sys.stdout.write(f"\r  [{done}/{total}] checking...")
        sys.stdout.flush()

    results = run_batch(accounts, workers=args.workers, on_progress=_progress)
    print("\n")
    print(f"{'#':<4} {'EMAIL':<35} {'STATUS':<16} MESSAGE")
    print("─" * 100)
    for r in results:
        c = COLOR.get(r["status"], "")
        print(f"{r['index']+1:<4} {r['email']:<35} {c}{r['status']:<16}{RESET} {r['message']}")
    print("─" * 100)
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n📊 SUMMARY")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {COLOR.get(k,'')}{k:<16}{RESET} {v}")
    if args.output:
        with Path(args.output).open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["line", "email", "password", "status", "message"])
            for r in results:
                w.writerow([r["index"] + 1, r["email"], r["password"], r["status"], r["message"]])
        print(f"\n💾 Saved to {args.output}")
    return 0


# ═══════════════════════════════════════════════════════════
# ENTRY POINT — WEB MODE IS DEFAULT
# ═══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Gmail IMAP Login Checker")
    ap.add_argument("input", nargs="?", help="Input file ('-' for stdin)")
    ap.add_argument("-o", "--output", help="CSV output file")
    ap.add_argument("-w", "--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--web", action="store_true", help="Start Web UI (default on Railway)")
    ap.add_argument("-p", "--port", type=int, defaul
