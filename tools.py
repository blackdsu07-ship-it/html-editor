import re
import json
import difflib
import html as htmlmod
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components

import tools
import style
import db

try:
    from streamlit_ace import st_ace
    HAS_ACE = True
except ImportError:
    HAS_ACE = False

st.set_page_config(page_title="HTML Online Viewer", page_icon="⚡", layout="wide",
                   initial_sidebar_state="collapsed")
style.apply()

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
def show_html(h, width, height):
    if hasattr(st, "iframe"):
        st.iframe(h, width=width or "stretch", height=height)
    else:
        components.html(h, width=width, height=height, scrolling=True)



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


# ---------- header + top nav ----------
st.markdown(
    '<div class="hero"><div class="logo">⚡</div><div><div class="brand">HTML Online Viewer</div>'
    '<div class="tag">preview · email checks · deliverability tools</div></div></div>',
    unsafe_allow_html=True)

NAV = {
    "🖥️ Viewer": None,
    "🌐 rDNS Generator": tools.rdns_generator,
    "🔍 FCrDNS Check": tools.rdns_checker,
    "🛡️ SPF · DKIM · DMARC": tools.dns_auth,
    "🚀 PowerMTA": tools.pmta,
}
with st.container(key="nav"):
    tool = st.radio("Tool", list(NAV), horizontal=True, label_visibility="collapsed")
if NAV[tool]:
    NAV[tool]()
    st.stop()

# ---------- viewer ----------
ss.setdefault("mode", "split")
ss.setdefault("ui_dark", False)
ss.setdefault("tree_open", True)


def set_mode(m):
    ss.mode = m


def tree_mode(o):
    ss.mode, ss.tree_open = "highlight", o


def do_format():
    ss.html = tools.beautify(ss.html)
    ss.ver += 1


def do_sample():
    ss.html = SAMPLE
    ss.ver += 1


def do_clear():
    ss.html = ""
    ss.ver += 1


def flip_dark():
    ss.ui_dark = not ss.ui_dark


rail_col, main_col = st.columns([1.25, 8])
with main_col:
    if ss.mode == "split":
        ed_col, pv_col = st.columns(2)
    else:
        ed_col, pv_col = None, st.container()
    chk = st.expander("Checks & tools")

if ed_col is not None:
    with ed_col:
        if HAS_ACE:
            new = st_ace(value=ss.html, language="html", theme="monokai" if ss.ui_dark else "chrome",
                         height=760, wrap=True, auto_update=True, key=f"ace_{ss.ver}")
        else:
            new = st.text_area("HTML", ss.html, height=760, key=f"ta_{ss.ver}")
        if new is not None:
            ss.html = new

with rail_col, st.container(key="vrail"):
    st.markdown('<div class="vtitle">HTML Online Viewer</div>', unsafe_allow_html=True)
    if ss.mode != "split":
        st.button("Back to editor", icon=":material/arrow_back:", on_click=set_mode, args=("split",), width="stretch")
    st.button("Preview (Full page)", icon=":material/visibility:", on_click=set_mode, args=("preview",), width="stretch")
    st.button("Highlight (Full page)", icon=":material/edit_note:", on_click=set_mode, args=("highlight",), width="stretch")
    st.button("Format", icon=":material/format_align_left:", on_click=do_format, width="stretch")
    st.button("Expand all", icon=":material/add_box:", on_click=tree_mode, args=(True,), width="stretch")
    st.button("Collapse all", icon=":material/indeterminate_check_box:", on_click=tree_mode, args=(False,), width="stretch")
    st.button("Sample", icon=":material/description:", on_click=do_sample, width="stretch")
    st.button("Clear", icon=":material/draft:", on_click=do_clear, width="stretch")
    with st.popover("Import from file", icon=":material/upload_file:", width="stretch"):
        up = st.file_uploader("Upload HTML", type=["html", "htm", "txt"])
        if up is not None:
            uid = f"{up.name}-{up.size}"
            if ss.last_upload != uid:
                ss.html = up.getvalue().decode("utf-8", errors="replace")
                ss.last_upload = uid
                ss.ver += 1
                st.rerun()
        url = st.text_input("Load from URL")
        if st.button("Fetch URL", width="stretch") and url:
            try:
                ss.html = fetch_url(url)
                ss.ver += 1
                st.rerun()
            except Exception as e:
                st.error(f"Fetch failed: {e}")
        if st.button("Load sample", width="stretch"):
            ss.html = SAMPLE
            ss.ver += 1
            st.rerun()
    st.download_button("Export to file", ss.html, "page.html", "text/html", icon=":material/download:", width="stretch")
    st.button("Dark mode", icon=":material/dark_mode:", on_click=flip_dark, width="stretch")
    st.markdown('<div class="vsep"></div>', unsafe_allow_html=True)
    with st.popover("Find & Replace", icon=":material/search:", width="stretch"):
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
    with st.popover("View options", icon=":material/tune:", width="stretch"):
        device = st.radio("Device", ["Desktop", "Tablet (768)", "Mobile (375)", "Custom"])
        custom_w = st.number_input("Custom width", 200, 1920, 600) if device == "Custom" else None
        height = st.slider("Preview height", 300, 2000, 900, 50)
        no_img = st.checkbox("Images off")
        dark = st.checkbox("Dark mode (rough sim)")
        http_imgs = st.checkbox("Load http:// images", True, help="Fetched through the server so they work on the https app")
    with st.popover("Merge data", icon=":material/data_object:", width="stretch"):
        merge_txt = st.text_area("key=value per line", "name=John\nemail=john@example.com", height=120)
    with st.popover("Templates", icon=":material/save:", width="stretch"):
        st.caption("☁️ Saved in Neon database" if db.enabled()
                   else "Session only. Add NEON_DATABASE_URL to secrets to save permanently.")
        try:
            nm = st.text_input("Name", key="tpl_name")
            if st.button("Save current") and nm.strip():
                db.save(nm.strip(), ss.html)
                st.toast("Template saved")
            saved = db.names()
            if saved:
                pick = st.selectbox("Saved", saved)
                if st.button("Load template"):
                    ss.html = db.load(pick) or ""
                    ss.ver += 1
                    st.rerun()
                if st.button("Delete template"):
                    db.remove(pick)
                    st.rerun()
                st.download_button("Export all (JSON)", json.dumps(db.export_all()), "templates.json")
            imp = st.file_uploader("Import JSON", type="json", key="tpl_imp")
            if imp is not None and ss.get("tpl_imp_id") != f"{imp.name}-{imp.size}":
                for k, v in json.loads(imp.getvalue()).items():
                    db.save(k, v)
                ss.tpl_imp_id = f"{imp.name}-{imp.size}"
                st.rerun()
        except Exception as e:
            st.error(f"Template storage error: {e}")
    with st.popover("Share link", icon=":material/share:", width="stretch"):
        if st.button("Generate link"):
            enc = tools.encode_share(ss.html)
            if len(enc) > 7000:
                st.error("Too large for a URL")
            else:
                st.query_params["h"] = enc
                st.success("Copy the URL from the address bar")
    with st.popover("Link tracking", icon=":material/link:", width="stretch"):
        tp = st.text_input("Params", "utm_source=email&utm_medium=bulk&utm_campaign=test")
        if st.button("Apply to all http(s) links"):
            ss.html = tools.track_links(ss.html, tp)
            ss.ver += 1
            st.rerun()

data = parse_data(merge_txt)
merged = apply_merge(ss.html, data)
shown = images_off(merged) if no_img else (tools.inline_http_images(merged) if http_imgs else merged)
if dark:
    shown = dark_sim(shown)
width = {"Desktop": None, "Tablet (768)": 768, "Mobile (375)": 375}.get(device, custom_w)

with pv_col:
    if ss.mode == "highlight":
        show_html(tools.highlight_tree(ss.html, ss.tree_open, ss.ui_dark), None, height)
    else:
        show_html(shown, width, height)

with chk:
    t_lint, t_links, t_text, t_spam, t_diff = st.tabs(["Lint", "Links", "Plain text", "Spam / ratio", "Diff"])

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
            st.dataframe(rows, width="stretch")
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
        try:
            tpl_names = db.names()
        except Exception:
            tpl_names = []
        src = st.selectbox("Compare against", ["Baseline snapshot", *tpl_names])
        base = ss.get("base") if src == "Baseline snapshot" else db.load(src)
        if base is None:
            st.info("Save a baseline first")
        else:
            page = difflib.HtmlDiff(wrapcolumn=60).make_file(
                base.splitlines(), ss.html.splitlines(), "Baseline", "Current", context=True, numlines=2)
            show_html(page, None, 600)
