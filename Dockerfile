FROM python:3.10

ENV TZ="Asia/Shanghai"

# 安装必要组件
RUN rm -f /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye main contrib non-free' >> /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye-updates main contrib non-free' >> /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye-backports main contrib non-free' >> /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bullseye-security main contrib non-free' >> /etc/apt/sources.list && \
    pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    apt update && \
    apt-get -y upgrade && \
    apt-get -y install libgl1-mesa-glx && \
    pip install poetry

# 安装依赖
WORKDIR /app
COPY ["pyproject.toml", "poetry.lock", "/app/"]
RUN poetry config virtualenvs.in-project true && \
    poetry install

# 添加源文件
COPY . /app

ENTRYPOINT ["poetry", "run", "python3", "main.py"]
