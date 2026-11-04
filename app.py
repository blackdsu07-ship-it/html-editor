import re
import json
import difflib
import html as htmlmod
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components

import tools

try:
    from streamlit_ace import st_ace
    HAS_ACE = True
except ImportError:
    HAS_ACE = False

st.set_page_config(page_title="HTML Online Viewer", layout="wide")

SAMPLE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sample</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;">
<div style="display:none;max-height:0;overflow:hidden;">Preheader text goes here</div>
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table width="600" cellpadding="20" cellspacing="0" style="background:#ffffff;font-family:Arial,sans-serif;">
<tr><td>
<h1>Hello {{name}}</h1>
<p>This is a sample email. Your email is [email].</p>
<img src="https://via.placeholder.com/560x120" alt="Banner" width="560">
<p><a href="https://example.com/offer">View offer</a></p>
</td></tr></table>
</td></tr></table>
</body>
</html>"""

ss = st.session_state
ss.setdefault("html", SAMPLE)
ss.setdefault("ver", 0)
ss.setdefault("last_upload", None)
ss.setdefault("tpls", {})
if "h" in st.query_params and not ss.get("share_loaded"):
    try:
        ss.html = tools.decode_share(st.query_params["h"])
    except Exception:
        pass
    ss.share_loaded = True


# ---------- helpers ----------
def parse_data(txt):
    d = {}
    for line in txt.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip():
                d[k.strip()] = v.strip()
    return d


def apply_merge(h, data):
    for k, v in data.items():
        k = re.escape(k)
        pats = [
            r"\{\{\s*" + k + r"\s*\}\}",
            r"\[\s*" + k + r"\s*\]",
            r"%%\s*" + k + r"\s*%%",
            r"\$\{\s*" + k + r"\s*\}",
        ]
        for p in pats:
            h = re.sub(p, lambda m: v, h)
    return h


def images_off(h):
    def repl(m):
        alt = re.search(r"alt\s*=\s*[\"']([^\"']*)", m.group(0), re.I)
        label = htmlmod.escape(alt.group(1)) if alt and alt.group(1) else "image blocked"
        return ('<span style="display:inline-block;border:1px solid #ccc;padding:4px;'
                'color:#666;font:12px sans-serif">' + label + "</span>")
    return re.sub(r"<img\b[^>]*>", repl, h, flags=re.I | re.S)


def dark_sim(h):
    css = ("<style>html{filter:invert(1) hue-rotate(180deg);background:#fff}"
           "img{filter:invert(1) hue-rotate(180deg)}</style>")
    return css + h


def to_text(h):
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", h)
    t = re.sub(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", r"\2 (\1)", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h[1-6]|li)>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def lint(raw, merged):
    out = []
    size = len(raw.encode("utf-8"))
    if size > 102 * 1024:
        out.append(("error", f"Size {size/1024:.1f} KB: Gmail clips above ~102 KB"))
    else:
        out.append(("ok", f"Size {size/1024:.1f} KB"))
    if not re.search(r"<!doctype", raw, re.I):
        out.append(("warn", "Missing DOCTYPE"))
    if not re.search(r"<meta[^>]+viewport", raw, re.I):
        out.append(("warn", "Missing viewport meta"))
    if not re.search(r"<title", raw, re.I):
        out.append(("warn", "Missing <title>"))
    body = re.split(r"<body", raw, flags=re.I)[-1][:3000]
    if not re.search(r"display\s*:\s*none|max-height\s*:\s*0", body, re.I):
        out.append(("warn", "No hidden preheader found near top of body"))
    imgs = re.findall(r"<img\b[^>]*>", raw, re.I | re.S)
    no_alt = [i for i in imgs if not re.search(r"\balt\s*=", i, re.I)]
    no_w = [i for i in imgs if not re.search(r"\bwidth\s*=", i, re.I)]
    if no_alt:
        out.append(("warn", f"{len(no_alt)} image(s) without alt"))
    if no_w:
        out.append(("warn", f"{len(no_w)} image(s) without width attribute"))
    checks = {
        r"display\s*:\s*(flex|grid)": "flex/grid (poor Outlook/Gmail support)",
        r"position\s*:\s*(absolute|fixed)": "position absolute/fixed",
        r"<script\b": "<script> (stripped by mail clients)",
        r"<form\b": "<form> (limited support)",
        r"<video\b|<audio\b": "video/audio tags",
        r"@font-face": "@font-face (limited support)",
        r"var\(|calc\(": "CSS var()/calc()",
        r"background-image\s*:": "CSS background-image (Outlook ignores)",
        r"<link[^>]+stylesheet": "external stylesheet",
    }
    for p, msg in checks.items():
        if re.search(p, raw, re.I):
            out.append(("warn", "Uses " + msg))
    for h in re.findall(r"href\s*=\s*[\"']([^\"']*)[\"']", raw, re.I):
        if h.strip() in ("", "#"):
            out.append(("warn", "Empty or '#' link found"))
            break
    left = set(re.findall(r"\{\{[^}]+\}\}|%%[^%]+%%", merged))
    if left:
        out.append(("warn", "Unreplaced merge tags: " + ", ".join(sorted(left))))
    return out


def fetch_url(u):
    req = Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def link_status(u):
    try:
        req = Request(u, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as r:
            return r.status
    except Exception as e:
        return str(getattr(e, "code", e))


# ---------- tool selector ----------
TOOLS = {
    "rDNS Generator": tools.rdns_generator,
    "rDNS / FCrDNS Checker": tools.rdns_checker,
    "SPF / DKIM / DMARC": tools.dns_auth,
    "Blacklist Checker": tools.blacklist,
    "PowerMTA Config": tools.pmta,
}
tool = st.sidebar.radio("Tool", ["HTML Viewer", *TOOLS])
if tool in TOOLS:
    TOOLS[tool]()
    st.stop()

# ---------- sidebar ----------
with st.sidebar:
    st.header("Load")
    up = st.file_uploader("Upload HTML", type=["html", "htm", "txt"])
    if up is not None:
        uid = f"{up.name}-{up.size}"
        if ss.last_upload != uid:
            ss.html = up.getvalue().decode("utf-8", errors="replace")
            ss.last_upload = uid
            ss.ver += 1
            st.rerun()
    url = st.text_input("Load from URL")
    c1, c2 = st.columns(2)
    if c1.button("Fetch", use_container_width=True) and url:
        try:
            ss.html = fetch_url(url)
            ss.ver += 1
            st.rerun()
        except Exception as e:
            st.error(f"Fetch failed: {e}")
    if c2.button("Sample", use_container_width=True):
        ss.html = SAMPLE
        ss.ver += 1
        st.rerun()

    st.header("Preview")
    device = st.radio("Device", ["Desktop", "Tablet (768)", "Mobile (375)", "Custom"])
    custom_w = st.number_input("Custom width", 200, 1920, 600) if device == "Custom" else None
    height = st.slider("Height", 300, 1400, 700, 50)
    no_img = st.checkbox("Images off")
    dark = st.checkbox("Dark mode (rough sim)")

    st.header("Merge data")
    merge_txt = st.text_area("key=value per line", "name=John\nemail=john@example.com", height=100)

    with st.expander("Templates (this session)"):
        nm = st.text_input("Name", key="tpl_name")
        if st.button("Save current") and nm:
            ss.tpls[nm] = ss.html
        if ss.tpls:
            pick = st.selectbox("Saved", list(ss.tpls))
            t1, t2 = st.columns(2)
            if t1.button("Load"):
                ss.html = ss.tpls[pick]
                ss.ver += 1
                st.rerun()
            if t2.button("Delete"):
                ss.tpls.pop(pick)
                st.rerun()
            st.download_button("Export all (JSON)", json.dumps(ss.tpls), "templates.json")
        imp = st.file_uploader("Import JSON", type="json", key="tpl_imp")
        if imp is not None and ss.get("tpl_imp_id") != f"{imp.name}-{imp.size}":
            try:
                ss.tpls.update(json.loads(imp.getvalue()))
                ss.tpl_imp_id = f"{imp.name}-{imp.size}"
                st.rerun()
            except Exception as e:
                st.error(f"Bad file: {e}")

    with st.expander("Share link"):
        if st.button("Generate link"):
            enc = tools.encode_share(ss.html)
            if len(enc) > 7000:
                st.error("Too large for a URL")
            else:
                st.query_params["h"] = enc
                st.success("Copy the URL from the address bar")

# ---------- main ----------
left, right = st.columns(2)

with left:
    st.subheader("Editor")
    with st.expander("Find & Replace"):
        f = st.text_input("Find", key="find")
        r = st.text_input("Replace with", key="repl")
        o1, o2 = st.columns(2)
        use_re = o1.checkbox("Regex")
        case = o2.checkbox("Case sensitive")
        if f:
            try:
                pat = re.compile(f if use_re else re.escape(f), 0 if case else re.I)
                n = len(pat.findall(ss.html))
                st.caption(f"{n} match(es)")
                if st.button("Replace all") and n:
                    ss.html = pat.sub(r if use_re else (lambda m: r), ss.html)
                    ss.ver += 1
                    st.rerun()
            except re.error as e:
                st.error(f"Bad regex: {e}")

    with st.expander("Add tracking params to links"):
        tp = st.text_input("Params", "utm_source=email&utm_medium=bulk&utm_campaign=test")
        if st.button("Apply to all http(s) links"):
            ss.html = tools.track_links(ss.html, tp)
            ss.ver += 1
            st.rerun()

    if HAS_ACE:
        new = st_ace(value=ss.html, language="html", theme="monokai", height=650,
                     wrap=True, auto_update=True, key=f"ace_{ss.ver}")
    else:
        new = st.text_area("HTML", ss.html, height=650, key=f"ta_{ss.ver}")
    if new is not None:
        ss.html = new

    d1, d2 = st.columns(2)
    d1.download_button("Download .html", ss.html, "page.html", "text/html", use_container_width=True)
    if d2.button("Clear", use_container_width=True):
        ss.html = ""
        ss.ver += 1
        st.rerun()

data = parse_data(merge_txt)
merged = apply_merge(ss.html, data)
shown = images_off(merged) if no_img else merged
if dark:
    shown = dark_sim(shown)

with right:
    t_prev, t_lint, t_links, t_text, t_spam, t_diff = st.tabs(
        ["Preview", "Lint", "Links", "Plain text", "Spam / ratio", "Diff"])

    with t_prev:
        width = {"Desktop": None, "Tablet (768)": 768, "Mobile (375)": 375}.get(device, custom_w)
        components.html(shown, width=width, height=height, scrolling=True)

    with t_lint:
        for lvl, msg in lint(ss.html, merged):
            {"ok": st.success, "warn": st.warning, "error": st.error}[lvl](msg)

    with t_links:
        links = re.findall(r"<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"']", merged, re.I)
        if links:
            rows = [{"url": u} for u in dict.fromkeys(links)]
            if st.button("Check status"):
                for row in rows:
                    row["status"] = link_status(row["url"]) if row["url"].startswith("http") else "-"
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("No links found")

    with t_text:
        st.text_area("Plain text version", to_text(merged), height=500)

    with t_spam:
        sp = tools.spam_report(merged)
        m = st.columns(4)
        m[0].metric("Text chars", sp["chars"])
        m[1].metric("Images", sp["images"])
        m[2].metric("Links", sp["links"])
        m[3].metric("ALL-CAPS words", sp["caps"])
        if sp["images"] and sp["chars"] < 200 * sp["images"]:
            st.warning(f"Low text-to-image ratio: {sp['chars']} chars / {sp['images']} images (aim for 200+ per image)")
        else:
            st.success("Text-to-image ratio OK")
        if sp["excl"] > 3:
            st.warning(f"{sp['excl']} exclamation marks")
        if sp["hits"]:
            st.warning("Spam trigger words found")
            st.dataframe([{"word": k, "count": v} for k, v in sp["hits"].items()])
        else:
            st.success("No spam trigger words found")

    with t_diff:
        if st.button("Save current as baseline"):
            ss.base = ss.html
        src = st.selectbox("Compare against", ["Baseline snapshot", *ss.tpls])
        base = ss.get("base") if src == "Baseline snapshot" else ss.tpls.get(src)
        if base is None:
            st.info("Save a baseline first")
        else:
            page = difflib.HtmlDiff(wrapcolumn=60).make_file(
                base.splitlines(), ss.html.splitlines(), "Baseline", "Current", context=True, numlines=2)
            components.html(page, height=600, scrolling=True)
