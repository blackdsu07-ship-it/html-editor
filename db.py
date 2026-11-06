"""Template storage: Neon Postgres when NEON_DATABASE_URL is in st.secrets, else session memory."""
from contextlib import closing

import streamlit as st

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def _url():
    try:
        return st.secrets["NEON_DATABASE_URL"]
    except Exception:
        return None


def enabled():
    return bool(psycopg2 and _url())


def _run(sql, args=(), fetch=False):
    with closing(psycopg2.connect(_url(), connect_timeout=10)) as c:
        with c, c.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall() if fetch else None


@st.cache_resource
def _init():
    _run("CREATE TABLE IF NOT EXISTS templates ("
         "name text PRIMARY KEY, html text NOT NULL, updated_at timestamptz DEFAULT now())")
    return True


@st.cache_data(ttl=60, show_spinner=False)
def _names_db():
    _init()
    return [r[0] for r in _run("SELECT name FROM templates ORDER BY updated_at DESC", fetch=True)]


@st.cache_data(ttl=60, show_spinner=False)
def _load_db(name):
    rows = _run("SELECT html FROM templates WHERE name=%s", (name,), fetch=True)
    return rows[0][0] if rows else None


def names():
    return _names_db() if enabled() else list(st.session_state.setdefault("tpls", {}))


def load(name):
    return _load_db(name) if enabled() else st.session_state.setdefault("tpls", {}).get(name)


def save(name, html):
    if enabled():
        _init()
        _run("INSERT INTO templates(name, html) VALUES (%s, %s) "
             "ON CONFLICT (name) DO UPDATE SET html = EXCLUDED.html, updated_at = now()", (name, html))
        _names_db.clear()
        _load_db.clear()
    else:
        st.session_state.setdefault("tpls", {})[name] = html


def remove(name):
    if enabled():
        _run("DELETE FROM templates WHERE name=%s", (name,))
        _names_db.clear()
        _load_db.clear()
    else:
        st.session_state.setdefault("tpls", {}).pop(name, None)


def export_all():
    return {n: load(n) for n in names()}
