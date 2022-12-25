FROM python:3.10
RUN pip config set global.index-url 'https://pypi.tuna.tsinghua.edu.cn/simple' && \
    pip install -U pip poetry
ENV TZ="Asia/Shanghai"
COPY . /app
WORKDIR /app
RUN poetry install
ENTRYPOINT ["poetry", "run", "python3", "main.py"]