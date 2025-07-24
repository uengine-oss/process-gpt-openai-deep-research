import os
from dotenv import load_dotenv

def pytest_configure():
    # test 환경으로 강제 설정
    os.environ['ENV'] = 'test'
    # .env.test 로드(override=True 로 덮어쓰기)
    load_dotenv('.env.test', override=True)