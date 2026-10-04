#!/usr/bin/env python3
import argparse
import json
import threading
import time
import uuid
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import websocket

HOST = "127.0.0.1"
PORT = 8765
DEBUG = "http://127.0.0.1:9222"

lock = threading.Lock()
queue = []
results = {}
tab_slots = {}
next_slot = 1
executor = ThreadPoolExecutor(max_workers=8)


def targets():
    with urllib.request.urlopen(DEBUG + "/json/list", timeout=2) as r:
        return [x for x in json.load(r) if x.get("type") == "page"]


def refresh_tabs():
    global next_slot
    ts = targets()
    live_ids = {t.get("id") for t in ts}

    with lock:
        for target_id in list(tab_slots):
            if target_id not in live_ids:
                del tab_slots[target_id]

        for t in ts:
            target_id = t.get("id")
            if target_id and target_id not in tab_slots:
                tab_slots[target_id] = next_slot
                next_slot += 1

    return ts


def tab_info(t):
    return {
        "tab": tab_slots.get(t.get("id")),
        "id": t.get("id"),
        "url": t.get("url", ""),
        "title": t.get("title", ""),
    }


def cdp(t, method, params=None):
    ws = websocket.create_connection(
        t["webSocketDebuggerUrl"],
        timeout=5,
        origin="http://127.0.0.1:9222",
        host="127.0.0.1:9222",
    )
    try:
        if method == "Runtime.evaluate":
            ws.send(json.dumps({
                "id": 1,
                "method": "Runtime.enable",
                "params": {},
            }))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == 1:
                    if "error" in m:
                        raise RuntimeError(m["error"].get("message", "CDP error"))
                    break
            req_id = 2
        else:
            req_id = 1

        ws.send(json.dumps({
            "id": req_id,
            "method": method,
            "params": params or {},
        }))

        while True:
            m = json.loads(ws.recv())
            if m.get("id") == req_id:
                if "error" in m:
                    raise RuntimeError(m["error"].get("message", "CDP error"))
                return m.get("result", {})
    finally:
        ws.close()


def ev(t, expr):
    return cdp(
        t,
        "Runtime.evaluate",
        {"expression": expr, "returnByValue": True},
    ).get("result", {}).get("value")


def input_text(t, text):
    """Type text through Firefox's CDP input pipeline so React receives input events."""
    for ch in text:
        cdp(
            t,
            "Input.dispatchKeyEvent",
            {
                "type": "char",
                "text": ch,
                "key": ch,
            },
        )


def target(p):
    ts = refresh_tabs()
    if not ts:
        raise RuntimeError("no Firefox tabs available")

    requested_tab = p.get("tab")
    if requested_tab is not None:
        try:
            requested_tab = int(requested_tab)
        except (TypeError, ValueError):
            raise RuntimeError("tab must be a number")

        for t in ts:
            if tab_slots.get(t.get("id")) == requested_tab:
                return t
        raise RuntimeError("tab %s is not open" % requested_tab)

    if p.get("target_id"):
        for t in ts:
            if t.get("id") == p["target_id"]:
                return t
        raise RuntimeError("requested target_id not found")

    if p.get("url"):
        for t in ts:
            if t.get("url") == p["url"]:
                return t
        raise RuntimeError("requested url not found")

    return ts[0]


def handle(p):
    action = p.get("action")

    if action == "list_tabs":
        return {"ok": True, "tabs": [tab_info(t) for t in refresh_tabs()]}

    t = target(p)

    if action == "get_active_tab":
        return {"ok": True, **tab_info(t)}

    if action == "read_page":
        data = json.loads(
            ev(
                t,
                'JSON.stringify({url:location.href,title:document.title,'
                'text:document.body?document.body.innerText:""})',
            ) or "{}"
        )
        return {"ok": True, "tab": tab_slots.get(t.get("id")), **data}

    if action == "read_selection":
        return {
            "ok": True,
            "tab": tab_slots.get(t.get("id")),
            "text": ev(t, "window.getSelection().toString()") or "",
        }

    if action == "find_text":
        s = json.dumps(p.get("text", ""), ensure_ascii=False)
        e = (
            """(()=>{const n=%s.toLowerCase(),b=document.body?document.body.innerText:'',
            i=b.toLowerCase().indexOf(n);return JSON.stringify({
            found:i>=0,context:i>=0?b.slice(Math.max(0,i-300),i+n.length+300):''})})()"""
            % s
        )
        return {
            "ok": True,
            "tab": tab_slots.get(t.get("id")),
            **json.loads(ev(t, e) or "{}"),
        }

    if action == "click":
        s = json.dumps(p.get("text", ""), ensure_ascii=False)
        e = (
            """(()=>{const n=%s.toLowerCase(),
            xs=[...document.querySelectorAll('button,a,input[type=button],input[type=submit],input[type=reset],[role=button]')],
            x0=xs.find(x=>{const v=(x.innerText||x.value||x.getAttribute('aria-label')||x.getAttribute('title')||'').trim().toLowerCase();
            return v===n||v.includes(n)});
            let x=x0;
            if(!x && (n==='отправить'||n==='send')){
                const candidates=[...document.querySelectorAll('[role=button]')].filter(b=>
                    !b.className.toString().includes('disabled') &&
                    b.className.toString().includes('ds-button--primary') &&
                    b.className.toString().includes('ds-button--filled') &&
                    b.className.toString().includes('ds-button--circle'));
                x=candidates[candidates.length-1];
            }
            if(!x)return JSON.stringify({clicked:false});
            x.scrollIntoView({block:'center',inline:'center'});
            const r=x.getBoundingClientRect();
            return JSON.stringify({clicked:true,text:x.innerText||x.value||x.getAttribute('aria-label')||'',
            x:r.left+r.width/2,y:r.top+r.height/2})})()"""
            % s
        )
        data = json.loads(ev(t, e) or "{}")
        if not data.get("clicked"):
            return {"ok": True, "tab": tab_slots.get(t.get("id")), **data}

        x = float(data["x"])
        y = float(data["y"])
        cdp(t, "Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
        })
        cdp(t, "Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        cdp(t, "Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        return {
            "ok": True,
            "tab": tab_slots.get(t.get("id")),
            "clicked": True,
            "text": data.get("text", ""),
        }

    if action == "type_text":
        text = p.get("text", "")
        state = json.loads(
            ev(
                t,
                """(()=>{const x=document.activeElement;
                return JSON.stringify({focused:!!x&&x.matches('input,textarea,[contenteditable=true]'),
                tag:x?.tagName||'',value:x?.value||''})})()""",
            ) or "{}"
        )
        if not state.get("focused"):
            return {
                "ok": True,
                "tab": tab_slots.get(t.get("id")),
                "typed": False,
                "error": "active element is not editable",
            }
        input_text(t, text)
        return {
            "ok": True,
            "tab": tab_slots.get(t.get("id")),
            "typed": True,
            "characters": len(text),
        }

    if action == "paste_text":
        s = json.dumps(p.get("text", ""), ensure_ascii=False)
        e = (
            """(()=>{const v=%s,x=document.activeElement;
            if(!x||!x.matches('input,textarea,[contenteditable=true]'))
            return JSON.stringify({typed:false,error:'active element is not editable'});
            if(x.isContentEditable){x.focus();document.execCommand('insertText',false,v)}
            else{x.value=v;x.dispatchEvent(new Event('input',{bubbles:true}));
            x.dispatchEvent(new Event('change',{bubbles:true}))}
            return JSON.stringify({typed:true})})()"""
            % s
        )
        return {
            "ok": True,
            "tab": tab_slots.get(t.get("id")),
            **json.loads(ev(t, e) or "{}"),
        }

    raise ValueError("unknown action: " + str(action))


def run_one(p):
    try:
        result = handle(p)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    with lock:
        results[p["id"]] = result


def worker():
    while True:
        with lock:
            p = queue.pop(0) if queue else None
        if not p:
            time.sleep(0.02)
            continue
        executor.submit(run_one, p)


class H(BaseHTTPRequestHandler):
    def sendj(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            try:
                ts = refresh_tabs()
                ok = True
            except Exception:
                ts = []
                ok = False
            return self.sendj(
                200,
                {
                    "ok": True,
                    "firefox": ok,
                    "tabs": len(ts),
                    "parallel_workers": 8,
                    "port": PORT,
                },
            )

        if path == "/tabs":
            try:
                return self.sendj(200, {"ok": True, "tabs": [tab_info(t) for t in refresh_tabs()]})
            except Exception as e:
                return self.sendj(503, {"ok": False, "error": str(e)})

        if path.startswith("/result/"):
            with lock:
                r = results.get(path.rsplit("/", 1)[-1])
            return self.sendj(200, r) if r else self.sendj(
                404, {"ok": False, "error": "result_not_ready"}
            )

        self.sendj(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if urlparse(self.path).path != "/command":
            return self.sendj(404, {"ok": False, "error": "not_found"})

        try:
            p = self.body()
            if not p.get("action"):
                raise ValueError("action is required")
            p["id"] = uuid.uuid4().hex
            with lock:
                queue.append(p)
            self.sendj(
                202,
                {
                    "ok": True,
                    "id": p["id"],
                    "tab": p.get("tab"),
                    "result_url": "http://%s:%s/result/%s" % (HOST, PORT, p["id"]),
                },
            )
        except Exception as e:
            self.sendj(400, {"ok": False, "error": str(e)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer((args.host, args.port), H).serve_forever()


if __name__ == "__main__":
    main()

[executed on device: leoVM (db283b0a-4aa9-4857-9dc8-18ec78e2df1f)]