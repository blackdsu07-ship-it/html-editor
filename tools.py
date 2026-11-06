import re
import textwrap
import io
import csv
import base64
import zlib
import ipaddress
import socket
import urllib.error
import urllib.request
from functools import lru_cache
from urllib.parse import urlparse
import html as htmlmod
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
import dns.resolver
import dns.reversename

R = dns.resolver.Resolver()
R.timeout = 3
R.lifetime = 5
MAX_IPS = 1024


# ---------- DNS helpers ----------
def q(name, rtype):
    try:
        return [x.to_text() for x in R.resolve(name, rtype)]
    except Exception:
        return []


def txt(name):
    return [t.replace('" "', "").strip('"') for t in q(name, "TXT")]


def ptr(ip):
    try:
        return [x.to_text().rstrip(".").lower() for x in R.resolve(dns.reversename.from_address(ip), "PTR")]
    except Exception:
        return []


def expand(text):
    """IPs, ranges (1.2.3.4-9) and CIDR -> list of IPv4 strings."""
    ips, bad = [], []
    for tok in re.split(r"[\s,;]+", text.strip()):
        if not tok:
            continue
        try:
            m = re.fullmatch(r"(\d+\.\d+\.\d+\.)(\d+)-(\d+)", tok)
            if m:
                a, b = int(m[2]), int(m[3])
                ipaddress.IPv4Address(m[1] + str(a))
                ipaddress.IPv4Address(m[1] + str(b))
                ips += [m[1] + str(i) for i in range(a, b + 1)]
            elif "/" in tok:
                net = ipaddress.ip_network(tok, strict=False)
                if net.version != 4 or net.num_addresses > MAX_IPS:
                    raise ValueError
                ips += [str(i) for i in (list(net.hosts()) or list(net))]
            else:
                ips.append(str(ipaddress.IPv4Address(tok)))
        except ValueError:
            bad.append(tok)
    return list(dict.fromkeys(ips))[:MAX_IPS], bad


def pairs(ips, domains, prefix, pattern, mode):
    out, n = [], len(ips)
    for i, ip in enumerate(ips):
        d = domains[i % len(domains)] if mode == "Rotate" else domains[i * len(domains) // n]
        a, b, c, e = ip.split(".")
        host = pattern
        for k, v in {"{ip}": ip.replace(".", "-"), "{last}": e, "{a}": a, "{b}": b, "{c}": c,
                     "{d}": e, "{prefix}": prefix, "{domain}": d}.items():
            host = host.replace(k, v)
        out.append((ip, host.lower()))
    return out


def render(pr, fmt):
    if fmt.startswith("Plain"):
        return "\n".join(f"{ip} {h}" for ip, h in pr)
    if fmt == "A records":
        return "\n".join(f"{h}. IN A {ip}" for ip, h in pr)
    if fmt == "BIND PTR records":
        return "\n".join(f"{dns.reversename.from_address(ip).to_text()} IN PTR {h}." for ip, h in pr)
    if fmt == "CSV":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ip", "hostname"])
        w.writerows(pr)
        return buf.getvalue()
    zones = {}
    for ip, h in pr:
        a, b, c, d = ip.split(".")
        zones.setdefault(f"{c}.{b}.{a}.in-addr.arpa.", []).append(f"{d} IN PTR {h}.")
    return "\n\n".join(f"$ORIGIN {z}\n" + "\n".join(r) for z, r in zones.items())


def rdns_inputs(k):
    ips_txt = st.text_area("IPs (one per line; ranges 1.2.3.4-9 and CIDR work)", height=160, key=k + "_ips")
    c1, c2 = st.columns(2)
    dom_txt = c1.text_input("Domain(s), comma separated", placeholder="steepbev.com", key=k + "_dom")
    prefix = c2.text_input("Subdomain prefix", placeholder="info", key=k + "_pre")
    with st.expander("Advanced"):
        pattern = st.text_input("Hostname pattern", "{prefix}{last}.{domain}", key=k + "_pat",
                                help="Placeholders: {prefix} {last} {a} {b} {c} {d} {ip} (dashed) {domain}")
        mode = st.radio("Multiple domains", ["Rotate", "Split evenly"], horizontal=True, key=k + "_mode")
    ips, bad = expand(ips_txt)
    domains = [d.strip().lower().strip(".") for d in re.split(r"[\s,;]+", dom_txt) if d.strip()]
    if bad:
        st.warning("Skipped: " + ", ".join(bad))
    return ips, domains, prefix.strip().lower(), pattern, mode


# ---------- tools ----------
def rdns_generator():
    st.title("rDNS Generator")
    ips, domains, prefix, pattern, mode = rdns_inputs("g")
    fmt = st.selectbox("Format", ["Plain (ip host)", "A records", "BIND PTR records", "BIND zone per /24", "CSV"])
    if not (ips and domains):
        st.info("Enter IPs and a domain")
        return
    out = render(pairs(ips, domains, prefix, pattern, mode), fmt)
    st.code(out, language=None)
    st.download_button("Download", out, "rdns.txt")


def check_ip(ip, helo):
    p = ptr(ip)
    fwd = [a for h in p for a in q(h, "A")]
    row = {"IP": ip, "PTR": ", ".join(p) or "-", "A (fwd)": ", ".join(dict.fromkeys(fwd)) or "-",
           "FCrDNS": "✅" if ip in fwd else "❌"}
    if helo:
        row["HELO"] = "✅" if helo in p else "❌"
    return row


def rdns_checker():
    st.title("rDNS / FCrDNS Checker")
    with st.form("chk"):
        ips_txt = st.text_area("IPs", height=160)
        helo = st.text_input("HELO/EHLO hostname (optional, compared to PTR)")
        go = st.form_submit_button("Check")
    if not go:
        return
    ips, bad = expand(ips_txt)
    if bad:
        st.warning("Skipped: " + ", ".join(bad))
    with ThreadPoolExecutor(20) as ex:
        rows = list(ex.map(lambda i: check_ip(i, helo.strip().lower()), ips))
    if not rows:
        return
    import pandas as pd
    ok = sum(r["FCrDNS"] == "✅" for r in rows)
    c1, c2 = st.columns(2)
    c1.success(f"✅ {ok} pass")
    c2.error(f"❌ {len(rows) - ok} fail") if len(rows) - ok else c2.success("❌ 0 fail")
    good = "background-color:#06402B;color:#34D399;font-weight:700;text-align:center"
    badc = "background-color:#4C0519;color:#FB7185;font-weight:700;text-align:center"
    df = pd.DataFrame(rows)
    marks = [c for c in ("FCrDNS", "HELO") if c in df.columns]

    def paint(d):
        s = pd.DataFrame("", index=d.index, columns=d.columns)
        for c in marks:
            s[c] = d[c].map(lambda v: good if v == "✅" else badc)
        s["IP"] = d["FCrDNS"].map(lambda v: "color:#34D399;font-weight:600" if v == "✅" else "color:#FB7185;font-weight:600")
        return s

    st.dataframe(df.style.apply(paint, axis=None), width="stretch", hide_index=True)


def dns_auth():
    st.title("SPF / DKIM / DMARC")
    with st.form("auth"):
        dom_txt = st.text_input("Domain(s), comma separated")
        sels = st.text_input("DKIM selectors", "default,selector1,selector2,google,k1,s1")
        go = st.form_submit_button("Check")
    if not go:
        return
    for d in [x.strip().lower() for x in dom_txt.split(",") if x.strip()]:
        st.subheader(d)
        spf = [t for t in txt(d) if t.lower().startswith("v=spf1")]
        if not spf:
            st.error("SPF: none found")
        else:
            if len(spf) > 1:
                st.error("SPF: multiple records (invalid)")
            rec = spf[0]
            st.code(rec, language=None)
            toks = [t.lstrip("+-~?").lower() for t in rec.split()[1:]]
            n = sum(t.startswith(("include:", "exists:", "redirect=", "ptr")) or t in ("a", "mx")
                    or t.startswith(("a:", "a/", "mx:", "mx/")) for t in toks)
            (st.error if n > 10 else st.success)(f"SPF top-level DNS lookups: {n}/10 (nested includes not counted)")
            end = rec.split()[-1].lower()
            if end in ("-all", "~all"):
                st.success(f"SPF ends with {end}")
            else:
                st.warning(f"SPF ends with '{end}' (expected -all or ~all)")
        dm = [t for t in txt("_dmarc." + d) if t.upper().startswith("V=DMARC1")]
        if not dm:
            st.error("DMARC: none found")
        else:
            st.code(dm[0], language=None)
            tags = dict(p.strip().split("=", 1) for p in dm[0].split(";") if "=" in p)
            pol = tags.get("p", "").lower()
            (st.warning if pol == "none" else st.success)(f"DMARC policy: p={pol or '?'}"
                                                         + (" (monitoring only)" if pol == "none" else ""))
            if "rua" not in tags:
                st.warning("DMARC: no rua reporting address")
        found = []
        for s in [x.strip() for x in sels.split(",") if x.strip()]:
            for t in txt(f"{s}._domainkey.{d}"):
                m = re.search(r"p=([A-Za-z0-9+/=]+)", t)
                found.append({"selector": s, "key": "present" if m else "revoked/empty", "record": t[:80] + "..."})
        if found:
            st.dataframe(found, width="stretch")
        else:
            st.warning("DKIM: no record found for the given selectors")


def pmta():
    st.title("PowerMTA Config")
    ips, domains, prefix, pattern, mode = rdns_inputs("p")
    c1, c2 = st.columns(2)
    vp = c1.text_input("VMTA name prefix", "vmta-", key="p_vp")
    pool = c2.text_input("Pool name", "pool1", key="p_pool")
    extra = st.text_area("Extra directives per VMTA (optional)", placeholder="max-smtp-out 20", key="p_extra")
    if not (ips and domains):
        st.info("Enter IPs and a domain")
        return
    blocks, names = [], []
    for ip, h in pairs(ips, domains, prefix, pattern, mode):
        name = vp + ip.replace(".", "-")
        names.append(name)
        body = f"    smtp-source-host {ip} {h}\n" + "".join(
            f"    {ln.strip()}\n" for ln in extra.splitlines() if ln.strip())
        blocks.append(f"<virtual-mta {name}>\n{body}</virtual-mta>")
    pool_blk = f"<virtual-mta-pool {pool}>\n" + "".join(f"    virtual-mta {n}\n" for n in names) + "</virtual-mta-pool>"
    out = "\n\n".join(blocks) + "\n\n" + pool_blk
    st.code(out, language=None)
    st.download_button("Download", out, "pmta-vmtas.conf")


# ---------- HTML viewer helpers ----------
def encode_share(h):
    return base64.urlsafe_b64encode(zlib.compress(h.encode(), 9)).decode()


def decode_share(s):
    return zlib.decompressobj().decompress(base64.urlsafe_b64decode(s.encode()), 2_000_000).decode()


def track_links(h, params):
    params = params.strip().lstrip("?&")
    keys = {p.split("=")[0] for p in params.split("&") if p}

    def f(m):
        url = m.group(2)
        if not re.match(r"https?://", url, re.I) or any(re.search(r"[?&]" + re.escape(k) + "=", url) for k in keys):
            return m.group(0)
        frag = ""
        if "#" in url:
            url, frag = url.split("#", 1)
            frag = "#" + frag
        return m.group(1) + url + ("&" if "?" in url else "?") + params + frag + m.group(3)

    return re.sub(r"(<a\b[^>]*?href\s*=\s*[\"'])([^\"']+)([\"'])", f, h, flags=re.I)


SPAM = ["free", "winner", "congratulations", "act now", "limited time", "urgent", "click here", "buy now",
        "guarantee", "no obligation", "risk free", "cash", "earn money", "make money", "credit", "loan",
        "casino", "lottery", "prize", "order now", "double your", "dear friend", "cheap", "discount",
        "save big", "apply now", "once in a lifetime", "no cost", "bonus", "offer expires"]


def spam_report(h):
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", h)
    t = htmlmod.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t).strip()
    low = t.lower()
    hits = {w: len(re.findall(r"\b" + re.escape(w) + r"\b", low)) for w in SPAM}
    return {"hits": {k: v for k, v in hits.items() if v}, "chars": len(t),
            "images": len(re.findall(r"<img\b", h, re.I)),
            "links": len(re.findall(r"<a\b[^>]*href", h, re.I)),
            "caps": len(re.findall(r"\b[A-Z]{4,}\b", t)), "excl": t.count("!")}


# ---------- http:// image loading for the preview ----------
def _public(host):
    try:
        return bool(host) and all(
            not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
            for ip in (ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(host, None)))
    except Exception:
        return False


class _Redir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _public(urlparse(newurl).hostname):
            raise urllib.error.URLError("blocked redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@lru_cache(maxsize=256)
def fetch_img(url):
    """Download an image server-side and return a data: URI (None if blocked/failed)."""
    try:
        if not _public(urlparse(url).hostname):
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.build_opener(_Redir).open(req, timeout=8) as r:
            ctype = r.headers.get_content_type()
            data = r.read(3_000_001)
        if not ctype.startswith("image/") or len(data) > 3_000_000:
            return None
        return f"data:{ctype};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return None


_IMG_PATS = [re.compile(r"(\b(?:src|background|poster)\s*=\s*[\"'])(http://[^\"']+)([\"'])", re.I),
             re.compile(r"(url\(\s*[\"']?)(http://[^\"')\s]+)([\"']?\s*\))", re.I)]


def inline_http_images(h):
    """Mixed-content fix: the app is https, so http:// images are blocked by the browser.
    Fetch them server-side and embed as data URIs (fallback: upgrade the URL to https)."""
    urls = list(dict.fromkeys(m.group(2) for p in _IMG_PATS for m in p.finditer(h)))[:40]
    if not urls:
        return h
    with ThreadPoolExecutor(8) as ex:
        got = dict(zip(urls, ex.map(fetch_img, urls)))

    def sub(m):
        d = got.get(m.group(2))
        return m.group(1) + (d or "https://" + m.group(2)[7:]) + m.group(3)

    for p in _IMG_PATS:
        h = p.sub(sub, h)
    return h


# ---------- format + highlight tree ----------
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_TOK = re.compile(r"(<!--.*?-->|<[^>]+>)", re.S)


def beautify(h):
    out, depth, raw = [], 0, None
    for tok in _TOK.split(h):
        if not tok or (not tok.strip() and not raw):
            continue
        pad = "  " * depth
        if tok.startswith("<!"):
            out.append(pad + tok.strip())
            continue
        m = re.match(r"<\s*(/?)\s*([A-Za-z][\w:-]*)", tok)
        if m:
            closing, name = m.group(1) == "/", m.group(2).lower()
            if closing:
                depth = max(depth - 1, 0)
                if name == raw:
                    raw = None
                out.append("  " * depth + tok.strip())
            else:
                out.append(pad + tok.strip())
                if name not in _VOID and not tok.rstrip().endswith("/>"):
                    depth += 1
                    if name in ("script", "style"):
                        raw = name
        elif raw:
            out.append(textwrap.indent(textwrap.dedent(tok.strip("\n")).rstrip(), pad))
        else:
            out.append(pad + re.sub(r"\s+", " ", tok).strip())
    return "\n".join(out) + "\n"


def highlight_tree(h, open_all=True, dark=False):
    esc = lambda s: htmlmod.escape(s, quote=False)

    def tag(tok):
        e = re.sub(r"([\w:-]+)(=)(\"[^\"]*\"|'[^']*')", r'<span class="a">\1</span>\2<span class="v">\3</span>', esc(tok))
        return re.sub(r"(&lt;/?)([\w:-]+)", r'\1<span class="t">\2</span>', e)

    out, stack, o = [], 0, " open" if open_all else ""
    for tok in _TOK.split(h):
        if not tok or not tok.strip():
            continue
        tok = tok.strip()
        if tok.startswith("<!"):
            out.append('<div class="c">%s</div>' % esc(tok))
        elif tok.startswith("<"):
            m = re.match(r"<\s*(/?)\s*([A-Za-z][\w:-]*)", tok)
            if not m:
                out.append("<div>%s</div>" % esc(tok))
            elif m.group(1) == "/":
                if stack:
                    stack -= 1
                    out.append('</div><div>%s</div></details>' % tag(tok))
                else:
                    out.append("<div>%s</div>" % tag(tok))
            elif m.group(2).lower() in _VOID or tok.endswith("/>"):
                out.append("<div>%s</div>" % tag(tok))
            else:
                stack += 1
                out.append('<details%s><summary>%s</summary><div class="k">' % (o, tag(tok)))
        else:
            out.append('<div class="x">%s</div>' % esc(tok))
    out.append("</div></details>" * stack)
    bg, fg, c1, c2, c3 = ("#1e1e1e", "#d4d4d4", "#7ee787", "#d2a8ff", "#a5d6ff") if dark else ("#fff", "#24292f", "#116329", "#8250df", "#0a3069")
    css = ("body{margin:0;padding:12px;background:%s;color:%s;font:13px/1.6 Consolas,monospace}"
           ".t{color:%s}.a{color:%s}.v{color:%s}.c{color:#6e7781}summary{cursor:pointer}"
           ".k{margin-left:18px;border-left:1px dotted #8887;padding-left:8px}" % (bg, fg, c1, c2, c3))
    return "<!doctype html><html><head><style>%s</style></head><body>%s</body></html>" % (css, "".join(out))
