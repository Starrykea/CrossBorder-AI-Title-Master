import streamlit.web.cli as stcli
import os, sys

def resolve_path(path):
    root_path = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(root_path, path)

if __name__ == "__main__":
    # 模拟命令行运行 streamlit
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("client_app.py"),
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())