FROM python:3.10
COPY . /app
WORKDIR /app
RUN pip config set global.index-url 'https://pypi.tuna.tsinghua.edu.cn/simple' && \
    pip install -U pip poetry
RUN poetry install
ENTRYPOINT ["poetry", "run", "python3", "/app/main.py"]