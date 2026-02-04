下面是一份**可以直接放到你仓库里的 `SETUP_CICD.md`**（Markdown 指导文档）。你把它交给 Codex VSCode 插件，让它**按文档逐步创建文件、修改配置、提交**即可。文档里我把“需要你填的变量/占位符”都标出来了，Codex 也能按步骤执行。

---

# SETUP_CICD.md — GitLab Python 后端：PyPI 包 + Docker 镜像 + 版本化发布（Tag 驱动）

> 目标：
>
> 1. 使用 GitLab 作为仓库
> 2. 标准化分支/发布/版本流程（Tag = 版本真相）
> 3. 自动构建并发布 **Python package** 到 GitLab PyPI Registry
> 4. 自动构建并发布 **Docker 镜像** 到 GitLab Container Registry
> 5. 用户可通过版本号：`pip install yourpkg==X.Y.Z` / `docker pull ...:X.Y.Z`
> 6. 容器挂载配置文件即可启动私有服务

---

## 0. 你需要先确定的变量（请填完）

请在本文件顶部记录这些值（Codex 也可以用它替换占位符）：

* `PACKAGE_NAME`：`<yourpkg>`（Python 包名，pip install 用这个）
* `MODULE_NAME`：`<yourpkg>`（Python import 用的顶层 module 名）
* `SERVICE_PORT`：`8080`（服务端口，默认 8080）
* `PYTHON_VERSION`：`3.12`
* 项目 GitLab 路径：`registry.gitlab.com/<group>/<project>`
* 配置文件路径（容器内）：`/etc/<yourpkg>/config.yaml`
* 配置环境变量名：`<YOURPKG>_CONFIG`（例如 `YOURPKG_CONFIG`）

> 约定：tag 采用 `vX.Y.Z`，例如 `v1.2.3`。
> 发布后镜像 tag 为 `X.Y.Z`（去掉 v 前缀）。

---

## 1) 仓库结构（Codex 要创建/调整）

目标结构示例：

```
.
├── .gitlab-ci.yml
├── Dockerfile
├── README.md
├── pyproject.toml
├── src/
│   └── <MODULE_NAME>/
│       ├── __init__.py
│       ├── server.py
│       ├── config.py
│       └── app.py              # 可选：如果你用 FastAPI
├── tests/
│   └── test_smoke.py
└── config.example.yaml
```

说明：

* 用 `src/` layout，避免 import 混乱
* `server.py` 提供可执行入口：`python -m <MODULE_NAME>.server`
* `config.py` 负责读取 YAML 配置文件 + 环境变量覆盖
* `Dockerfile` 在 CI 的 tag pipeline 中安装 `dist/*.whl`

---

## 2) Python 打包配置（pyproject.toml）

### 2.1 创建/更新 `pyproject.toml`

要求：

* 使用 `setuptools + setuptools-scm`：版本来自 git tag
* 包名为 `PACKAGE_NAME`
* 源码目录：`src/`

创建内容（把 `<...>` 替换为你的变量）：

```toml
[build-system]
requires = ["setuptools>=68", "setuptools-scm>=8", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "<PACKAGE_NAME>"
dynamic = ["version"]
description = "Private backend service package"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
  "pyyaml>=6.0",
  # 如果你用 FastAPI：
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "pydantic>=2.0",
]

[project.optional-dependencies]
test = [
  "pytest>=8.0",
  "ruff>=0.6",
]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools_scm]
version_scheme = "no-guess-dev"
local_scheme = "no-local-version"
```

> 注意：setuptools-scm 会把 `v1.2.3` 解析成版本 `1.2.3`。

---

## 3) 服务入口与配置系统（可私有部署）

### 3.1 创建 `src/<MODULE_NAME>/config.py`

目标：

* 默认读取：环境变量 `<YOURPKG>_CONFIG` 指定的 yaml 路径
* 支持未提供配置时用默认值启动（可最小化）
* 你可以后续换成更严格 schema（pydantic）

参考实现：

```python
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
import yaml

@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("config yaml must be a mapping")
    return data

def load_settings(env_var: str, default_path: Optional[str] = None) -> Settings:
    path = os.getenv(env_var) or default_path
    data: Dict[str, Any] = {}
    if path and os.path.exists(path):
        data = load_yaml(path)

    # 简单映射，后续可替换为 pydantic
    return Settings(
        host=str(data.get("host", "0.0.0.0")),
        port=int(data.get("port", 8080)),
        log_level=str(data.get("log_level", "info")),
    )
```

### 3.2 创建 `src/<MODULE_NAME>/server.py`

目标：

* `python -m <MODULE_NAME>.server` 可启动
* 如果采用 FastAPI：启动 uvicorn
* 读取配置 env var `<YOURPKG>_CONFIG`

示例（FastAPI）：

```python
from __future__ import annotations
import os
import uvicorn
from .config import load_settings
from .app import app

ENV_VAR = "<YOURPKG>_CONFIG"  # 替换成你的环境变量名

def main():
    settings = load_settings(ENV_VAR, default_path=None)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )

if __name__ == "__main__":
    main()
```

### 3.3 创建 `src/<MODULE_NAME>/app.py`

最小 FastAPI 示例：

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}
```

---

## 4) 示例配置文件

### 4.1 `config.example.yaml`

```yaml
host: "0.0.0.0"
port: 8080
log_level: "info"
```

---

## 5) Dockerfile（从 wheel 安装，干净可复现）

创建 `Dockerfile`（替换 `<SERVICE_PORT>`）：

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir -U pip

# CI 在 tag 流水线会先 build 出 dist/*.whl，然后 docker build 时 COPY 进来
COPY dist/*.whl /tmp/pkg.whl
RUN pip install --no-cache-dir /tmp/pkg.whl && rm -f /tmp/pkg.whl

RUN useradd -m appuser
USER appuser

EXPOSE <SERVICE_PORT>

# 约定：python -m <MODULE_NAME>.server 作为启动入口
ENTRYPOINT ["python", "-m", "<MODULE_NAME>.server"]
```

---

## 6) GitLab CI/CD：Tag 发布包 + 镜像（最小可用）

创建 `.gitlab-ci.yml`，并替换 `<PACKAGE_NAME>`：

```yaml
stages:
  - lint
  - test
  - build
  - publish
  - docker
  - release

workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH
    - if: $CI_COMMIT_TAG

variables:
  PYTHON_VERSION: "3.12"
  PACKAGE_NAME: "<PACKAGE_NAME>"

# ---------------- 分支 / MR：质量检查 ----------------
lint:
  stage: lint
  image: python:${PYTHON_VERSION}-slim
  rules:
    - if: $CI_COMMIT_TAG
      when: never
    - when: on_success
  script:
    - pip install -U pip
    - pip install ruff
    - ruff check .
    - ruff format --check .

test:
  stage: test
  image: python:${PYTHON_VERSION}-slim
  rules:
    - if: $CI_COMMIT_TAG
      when: never
    - when: on_success
  script:
    - pip install -U pip
    - pip install -e .[test] || pip install -e .
    - pytest -q

# ---------------- tag：构建 Python 包 ----------------
build_pkg:
  stage: build
  image: python:${PYTHON_VERSION}-slim
  rules:
    - if: $CI_COMMIT_TAG
  script:
    - pip install -U pip
    - pip install build
    - python -m build
    - ls -lah dist
  artifacts:
    paths:
      - dist/
    expire_in: 365 days

# ---------------- tag：发布到 GitLab PyPI Registry ----------------
publish_pypi:
  stage: publish
  image: python:${PYTHON_VERSION}-slim
  rules:
    - if: $CI_COMMIT_TAG
  needs: ["build_pkg"]
  script:
    - pip install -U pip
    - pip install twine
    - |
      python -m twine upload \
        --repository-url "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/pypi" \
        -u gitlab-ci-token \
        -p "${CI_JOB_TOKEN}" \
        dist/*

# ---------------- tag：构建并推送 Docker 镜像 ----------------
docker_build_push:
  stage: docker
  image: docker:27
  services:
    - docker:27-dind
  rules:
    - if: $CI_COMMIT_TAG
  needs: ["build_pkg"]
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
  before_script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
  script:
    - VERSION="${CI_COMMIT_TAG#v}"
    - docker build -t "${CI_REGISTRY_IMAGE}:${VERSION}" -t "${CI_REGISTRY_IMAGE}:latest" .
    - docker push "${CI_REGISTRY_IMAGE}:${VERSION}"
    - docker push "${CI_REGISTRY_IMAGE}:latest"

# ---------------- tag：创建 GitLab Release（可选） ----------------
create_release:
  stage: release
  image: alpine:3.20
  rules:
    - if: $CI_COMMIT_TAG
  needs: ["docker_build_push", "publish_pypi"]
  before_script:
    - apk add --no-cache curl jq
  script:
    - VERSION="${CI_COMMIT_TAG#v}"
    - NOTES="Release ${CI_COMMIT_TAG}\n\n- PyPI: ${PACKAGE_NAME}==${VERSION}\n- Docker: ${CI_REGISTRY_IMAGE}:${VERSION}"
    - |
      curl --fail --request POST \
        --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
        --header "Content-Type: application/json" \
        --data "$(jq -n \
          --arg name "${CI_COMMIT_TAG}" \
          --arg tag_name "${CI_COMMIT_TAG}" \
          --arg description "$NOTES" \
          '{name:$name, tag_name:$tag_name, description:$description}')" \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/releases"
```

---

## 7) GitLab 项目设置（必须手动点几下）

在 GitLab 项目里做这些设置：

1. **开启 Container Registry**

   * Settings → General → Visibility, project features, permissions → Container Registry（确保开启）

2. **Protected Branches**

   * main：只允许 Maintainers push，合并必须 MR
   * release/*：只允许 Maintainers push

3. **Protected Tags**

   * Pattern：`v*`
   * 只允许 Maintainers 创建 tag

4. **MR 质量闸门**

   * Settings → Merge requests：启用 “Pipelines must succeed”
   * 可以加 Code Owners / approvals（按团队需要）

---

## 8) 发布流程（操作手册）

### 8.1 开发与合并

* feature 分支开发 → 提 MR → 合并到 main（或 develop）
* MR pipeline 通过（lint/test 都绿）

### 8.2 发布版本（触发自动化）

在 main 上创建 tag：

```bash
git checkout main
git pull
git tag v1.2.3
git push origin v1.2.3
```

触发 tag pipeline 后，会自动：

* build：生成 dist/*.whl、dist/*.tar.gz
* publish：上传到 GitLab PyPI Registry
* docker：构建并推送镜像到 GitLab Container Registry
* release：创建 Release（可选）

---

## 9) 用户如何按版本安装/拉取

### 9.1 pip 安装（GitLab PyPI Registry）

在部署环境准备一个 token（推荐 Deploy Token / 或 PAT），然后：

```bash
pip install \
  --index-url "https://__token__:<TOKEN>@gitlab.com/api/v4/projects/<PROJECT_ID>/packages/pypi/simple" \
  <PACKAGE_NAME>==1.2.3
```

> 注：PROJECT_ID 在 GitLab 项目主页可看到。
> token 权限至少需要读取 package registry / API（具体按 GitLab 版本和配置可能略有差异）。

### 9.2 docker 拉取与启动

```bash
docker pull registry.gitlab.com/<group>/<project>:1.2.3

docker run -d --name <PACKAGE_NAME> \
  -p 8080:8080 \
  -v $(pwd)/config.yaml:/etc/<PACKAGE_NAME>/config.yaml:ro \
  -e <YOURPKG>_CONFIG=/etc/<PACKAGE_NAME>/config.yaml \
  registry.gitlab.com/<group>/<project>:1.2.3
```

---

## 10) 最小 smoke test（保证 CI 有东西可跑）

创建 `tests/test_smoke.py`：

```python
def test_smoke():
    assert True
```

---

## 11) 验收清单（Codex 执行完后你怎么验）

1. 本地能 build：

   * `python -m build` 生成 `dist/`
2. 本地能启动：

   * `python -m <MODULE_NAME>.server`
3. CI 分支 pipeline 绿（lint/test）
4. 打 tag `v0.1.0` 后：

   * CI 生成 dist
   * PyPI Registry 里能看到版本 `0.1.0`
   * Container Registry 里能看到镜像 tag `0.1.0`、`latest`
   * Release 页面（若开启）有条目

---

## 12) Codex 执行指令建议（给它的任务拆分）

你可以把下面这段直接发给 Codex（逐条执行）：

1. 根据本文件的结构创建目录与文件：`src/<MODULE_NAME>/...`、`tests/`、`Dockerfile`、`.gitlab-ci.yml`、`config.example.yaml`。
2. 把 `pyproject.toml` 配好（setuptools-scm + src layout），并把 `<...>` 占位符替换为真实值。
3. 实现 `config.py/server.py/app.py` 让 `python -m <MODULE_NAME>.server` 能启动并暴露 `/healthz`。
4. 确保 `ruff` 与 `pytest` 可运行，CI jobs 不会报错。
5. 本地执行：`python -m build` 通过。
6. 本地执行：构建 Docker：`docker build -t test:local .`（需要先 build 出 dist/，可在本地先 `python -m build`）。
7. 提交代码。

---

如果你愿意，我也可以把这份文档里的占位符直接替换成你项目的真实值——你只需要回复我 4 个值即可（不需要额外讨论）：

* `PACKAGE_NAME`（pip 的名字）
* `MODULE_NAME`（import 的名字）
* 是否确定用 FastAPI（是/否）
* 服务端口（默认 8080 是否要改）
