import re
import io
import csv
import base64
import zlib
import ipaddress
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
    row = {"ip": ip, "ptr": ", ".join(p) or "-", "A of PTR": ", ".join(dict.fromkeys(fwd)) or "-",
           "FCrDNS": "PASS" if ip in fwd else "FAIL"}
    if helo:
        row["HELO match"] = "PASS" if helo in p else "FAIL"
    return row


def rdns_checker():
    st.title("rDNS / FCrDNS Checker")
    with st.form("chk"):
        ips_txt = st.text_area("IPs", height=160)
        helo = st.text_input("HELO/EHLO hostname (optional, compared to PTR)")
        go = st.form_submit_button("Check")
    if go:
        ips, bad = expand(ips_txt)
        if bad:
            st.warning("Skipped: " + ", ".join(bad))
        with ThreadPoolExecutor(20) as ex:
            rows = list(ex.map(lambda i: check_ip(i, helo.strip().lower()), ips))
        if rows:
            ok = sum(r["FCrDNS"] == "PASS" for r in rows)
            st.metric("FCrDNS pass", f"{ok}/{len(rows)}")
            st.dataframe(rows, use_container_width=True)


DNSBL = ["zen.spamhaus.org", "b.barracudacentral.org", "bl.spamcop.net", "dnsbl.sorbs.net",
         "psbl.surriel.com", "dnsbl-1.uceprotect.net", "bl.mailspike.net"]


SPAMHAUS = {"127.0.0.2": "SBL", "127.0.0.3": "CSS", "127.0.0.4": "XBL", "127.0.0.7": "XBL",
            "127.0.0.9": "SBL DROP", "127.0.0.10": "PBL", "127.0.0.11": "PBL"}


def dnsbl(ip, zone, key=""):
    host = ".".join(reversed(ip.split(".")))
    z = f"{key}.zen.dq.spamhaus.net" if key and zone == "zen.spamhaus.org" else zone
    try:
        a = [x.to_text() for x in R.resolve(f"{host}.{z}", "A")]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return "ok"
    except Exception:
        return "error"
    if any(x.startswith("127.255.255.") for x in a):
        return "blocked"
    if zone == "zen.spamhaus.org":
        return "LISTED " + "/".join(dict.fromkeys(SPAMHAUS.get(x, x) for x in a))
    return "LISTED"


def blacklist():
    st.title("Blacklist Checker")
    with st.form("bl"):
        ips_txt = st.text_area("IPs", height=140)
        zones = st.multiselect("DNSBLs", DNSBL, DNSBL)
        key = st.text_input("Spamhaus DQS key (optional, fixes 'blocked'/'error')", type="password")
        go = st.form_submit_button("Check")
    if go:
        ips, bad = expand(ips_txt)
        if len(ips) > 50:
            st.warning("Limited to the first 50 IPs")
            ips = ips[:50]
        jobs = [(i, z) for i in ips for z in zones]
        with ThreadPoolExecutor(30) as ex:
            res = list(ex.map(lambda j: dnsbl(*j, key.strip()), jobs))
        table = {i: {"ip": i} for i in ips}
        for (i, z), r in zip(jobs, res):
            table[i][z] = r
        rows = list(table.values())
        for r in rows:
            r["listed"] = sum(v.startswith("LISTED") for k, v in r.items() if k not in ("ip", "listed"))
        st.dataframe(rows, use_container_width=True)
        if "blocked" in res or "error" in res:
            st.warning("Some results are UNKNOWN, not clean: 'blocked' = DNSBL refused this resolver, 'error' = lookup "
                       "failed/timed out. Spamhaus blocks shared/cloud DNS; use a free Spamhaus DQS key above.")


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
            st.dataframe(found, use_container_width=True)
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
