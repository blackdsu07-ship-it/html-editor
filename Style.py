import streamlit as st

CSS = """
<style>
.stApp{background:
  radial-gradient(1100px 560px at 8% -10%,#2a1b5e66,transparent),
  radial-gradient(900px 500px at 100% 0%,#0e749044,transparent),
  radial-gradient(800px 500px at 50% 110%,#be185d33,transparent),#0B1020;}
#MainMenu,footer{visibility:hidden}
h1{background:linear-gradient(90deg,#8B5CF6,#06B6D4 55%,#F472B6);-webkit-background-clip:text;
   -webkit-text-fill-color:transparent;font-weight:800!important;letter-spacing:-.5px}
h2,h3{color:#C4B5FD!important}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#141B34,#1b1442);border-right:1px solid #ffffff14}
[data-testid="stSidebar"] [role="radiogroup"] label{padding:6px 10px;border-radius:10px;transition:.15s}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:#8B5CF633}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{
  background:linear-gradient(135deg,#8B5CF6,#06B6D4);color:#fff;border:0;border-radius:10px;
  font-weight:600;transition:.2s}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{
  transform:translateY(-1px);box-shadow:0 6px 18px #8B5CF655;color:#fff}
button[data-baseweb="tab"]{font-weight:600;border-radius:10px 10px 0 0}
button[data-baseweb="tab"][aria-selected="true"]{color:#22D3EE}
[data-baseweb="tab-highlight"]{background:linear-gradient(90deg,#8B5CF6,#06B6D4)!important;height:3px}
[data-testid="stMetric"]{background:linear-gradient(135deg,#8B5CF626,#06B6D422);
  border:1px solid #ffffff1f;border-radius:14px;padding:12px 16px}
[data-testid="stExpander"]{border:1px solid #ffffff1a;border-radius:12px;background:#ffffff08}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{border-radius:10px!important}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within{box-shadow:0 0 0 2px #8B5CF699}
[data-testid="stAlert"]{border-radius:12px}
[data-testid="stCode"] pre{border-radius:12px;border:1px solid #ffffff14}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;border:1px solid #ffffff1f}
iframe{border-radius:12px;border:1px solid #ffffff1f}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:linear-gradient(#8B5CF6,#06B6D4);border-radius:8px}
</style>
"""


def apply():
    st.markdown(CSS, unsafe_allow_html=True)
