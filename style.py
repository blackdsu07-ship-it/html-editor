import streamlit as st

CSS = """
<style>
.stApp{background:
  radial-gradient(1000px 520px at 5% -10%,#5b21b655,transparent),
  radial-gradient(900px 500px at 100% 0%,#0891b238,transparent),
  radial-gradient(800px 500px at 50% 115%,#be185d33,transparent),#070A14;}
#MainMenu,footer{visibility:hidden}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"]{display:none!important}
[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1.4rem;max-width:1600px}

/* hero */
.hero{display:flex;gap:16px;align-items:center;padding:14px 22px;border-radius:20px;margin-bottom:14px;
  background:#ffffff0a;border:1px solid #ffffff1a;backdrop-filter:blur(12px)}
.logo{width:54px;height:54px;border-radius:16px;display:grid;place-items:center;font-size:26px;
  background:linear-gradient(135deg,#8B5CF6,#EC4899);box-shadow:0 0 26px #8B5CF688}
.brand{font-size:1.8rem;font-weight:800;letter-spacing:-.5px;line-height:1.1;
  background:linear-gradient(90deg,#A78BFA,#22D3EE,#F472B6,#A78BFA);background-size:200% auto;
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:shine 6s linear infinite}
.tag{color:#94A3B8;font-size:.9rem}
@keyframes shine{to{background-position:200% center}}

/* top nav pills */
.st-key-nav [role="radiogroup"]{gap:6px;display:inline-flex;flex-wrap:wrap;padding:6px;border-radius:999px;
  background:#ffffff0d;border:1px solid #ffffff1a;backdrop-filter:blur(10px)}
.st-key-nav label{margin:0;padding:8px 18px;border-radius:999px;cursor:pointer;transition:.2s}
.st-key-nav label>div:first-child{display:none}
.st-key-nav label p{margin:0;font-weight:600;color:#CBD5E1}
.st-key-nav label:hover{background:#ffffff14}
.st-key-nav label:has(input:checked){background:linear-gradient(135deg,#8B5CF6,#EC4899);box-shadow:0 4px 18px #8B5CF677}
.st-key-nav label:has(input:checked) p{color:#fff}

/* toolbar popovers */
.st-key-toolbar{margin:10px 0 6px}
.st-key-toolbar [data-testid="stPopover"]>button{background:#ffffff0d;border:1px solid #ffffff26;border-radius:12px;
  color:#E2E8F0;font-weight:600;backdrop-filter:blur(8px);transition:.2s}
.st-key-toolbar [data-testid="stPopover"]>button:hover{border-color:#22D3EE;box-shadow:0 0 16px #22D3EE55;color:#fff}

/* glass panels */
.st-key-panel_l,.st-key-panel_r{background:#ffffff08;border:1px solid #ffffff1f;border-radius:18px;padding:16px;
  backdrop-filter:blur(14px);box-shadow:0 10px 40px #00000066}

h1{background:linear-gradient(90deg,#A78BFA,#22D3EE 55%,#F472B6);-webkit-background-clip:text;
   -webkit-text-fill-color:transparent;font-weight:800!important}
h2,h3{color:#C4B5FD!important}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{
  background:linear-gradient(135deg,#8B5CF6,#06B6D4);color:#fff;border:0;border-radius:10px;font-weight:600;transition:.2s}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{
  transform:translateY(-1px);box-shadow:0 6px 18px #8B5CF677;color:#fff}
button[data-baseweb="tab"]{font-weight:600}
button[data-baseweb="tab"][aria-selected="true"]{color:#22D3EE}
[data-baseweb="tab-highlight"]{background:linear-gradient(90deg,#8B5CF6,#EC4899)!important;height:3px}
[data-testid="stMetric"]{background:linear-gradient(135deg,#8B5CF626,#EC489922);
  border:1px solid #ffffff1f;border-radius:14px;padding:12px 16px}
[data-testid="stExpander"]{border:1px solid #ffffff1a;border-radius:12px;background:#ffffff08}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{border-radius:10px!important}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within{box-shadow:0 0 0 2px #8B5CF699}
[data-testid="stAlert"]{border-radius:12px}
[data-testid="stCode"] pre{border-radius:12px;border:1px solid #ffffff14}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;border:1px solid #ffffff1f}
iframe{border-radius:12px;border:1px solid #ffffff1f;background:#fff}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:linear-gradient(#8B5CF6,#EC4899);border-radius:8px}

/* viewer rail (onlineviewer-style) */
.st-key-vrail{background:#2b2b2b;border-radius:10px;padding:12px 10px;gap:.45rem}
.vtitle{color:#ececec;text-align:center;font-size:15px;padding:6px 0 4px}
.vsep{height:10px}
.st-key-vrail button{background:#e9e9e9!important;color:#1d1d1d!important;border:1px solid #9a9a9a!important;
  border-radius:4px!important;font-weight:500;justify-content:flex-start;box-shadow:none!important;transform:none!important}
.st-key-vrail button:hover{background:#fff!important;color:#000!important;border-color:#fff!important}
.st-key-vrail button *{color:#1d1d1d!important;fill:#1d1d1d!important}
</style>
"""


def apply():
    st.markdown(CSS, unsafe_allow_html=True)
