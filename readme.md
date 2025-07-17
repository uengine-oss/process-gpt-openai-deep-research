uv venv
uv pip install -r requirements.txt
source .venv/Scripts/activate
deactivate

uv run test_deep_research.py > output.log 2>&1
python main.py > output.log 2>&1
PYTHONUTF8=1 python -X utf8 test_deep_research.py > output.log 2>&1
python -u test_deep_research.py > output.log 2>&1