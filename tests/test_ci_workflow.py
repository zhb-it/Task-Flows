"""CI workflow 契约测试（TASK-061；开发文档 §4 / §37 / §44）。

这些用例**不联网、不跑 Actions**：只解析 `.github/workflows/ci.yml`（以及它引用
的 `Dockerfile` / `requirements*.txt` / `pyproject.toml` / compose 文件），把「CI
必须成立的性质」固化成断言。理由与 `tests/test_prod_compose.py` 完全一样——YAML 里
的错误不会在本地报错，只会在推送几分钟后以「红的 run」的形式出现，而那条反馈路径
足够慢，慢到让人习惯性地「再跑一次试试」。

最要紧的两条性质：

1. **service 端口必须匹配测试里硬编码的地址**。测试套件里有 40 个文件写死了
   `127.0.0.1:5433` / `127.0.0.1:6389`；CI 的 service 映射一旦被改（比如有人
   「顺手对齐成 5432」），全量用例会集体连接失败——而这件事在本地跑不出来。
2. **迁移可逆性步骤必须真的在跑**（§37）。`downgrade()` 的腐坏平时无人察觉，
   只有真需要回滚时才炸；把三步命令的顺序钉死，是让「有人删掉其中一步」这件事
   变成一个会红的测试。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
REQUIREMENTS_DEV = PROJECT_ROOT / "requirements-dev.txt"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
DEV_COMPOSE = PROJECT_ROOT / "docker-compose.yml"
PROD_COMPOSE = PROJECT_ROOT / "docker-compose.prod.yml"
TESTS_DIR = PROJECT_ROOT / "tests"

#: 三个 job 各自的职责，与 §44 的四步（安装依赖 → lint → pytest → docker build）对应。
EXPECTED_JOBS = {"lint", "test", "docker-build"}

#: 测试套件**真的要去连**的后端端口 —— CI 必须提供对应的 service。
#: 数值来自测试里的模块级常量，不是这里凭空定的。
REQUIRED_SERVICE_PORTS = {5433: "postgres", 6389: "redis"}

#: 测试里出现、但**刻意不需要**任何服务监听的端口。
#: 如果断言写成「测试里出现的端口都得有服务」，这三个会被误判成缺口。
KNOWN_NON_SERVICE_PORTS = {
    1: "test_celery_app / test_rate_limit 用它验证「Redis 拒绝连接」时的降级行为",
    6399: "test_redis.py 用它验证 Redis 不可用时的降级行为",
    8000: "test_nginx_config.py 里是容器内 app 的监听端口（Nginx upstream 语义），"
    "且只出现在说明文字中，不是运行时连接目标",
}


# ---------------------------------------------------------------------------
# 解析辅助
# ---------------------------------------------------------------------------


def _load_workflow() -> tuple[dict, str]:
    """返回 (解析后的 workflow, 原文)。"""
    raw = WORKFLOW.read_text(encoding="utf-8")
    return yaml.safe_load(raw), raw


def _triggers(doc: dict) -> dict:
    """取 `on:` 段。

    PyYAML 按 YAML 1.1 解析，裸 `on` 会被读成**布尔 True** 而不是字符串 "on"
    （`yes`/`no`/`on`/`off` 都算布尔）。两种键都试一下——这是 PyYAML 的既知行为，
    不是本文件或 workflow 写错了。
    """
    return doc.get("on") or doc.get(True) or {}


def _step_text(step: dict) -> str:
    """把一步的所有文本字段拼起来，便于做包含判断。"""
    parts = [str(step.get("name") or ""), str(step.get("uses") or ""), str(step.get("run") or "")]
    return "\n".join(parts)


def _jobs_of(workflow: dict, name: str) -> dict:
    """按 job 名取 job 定义。"""
    return workflow["jobs"][name]


def _step_index(job: dict, needle: str) -> int:
    """返回含 `needle` 的步骤下标；找不到就断言失败（而不是返回 -1 让后续断言含糊）。"""
    for index, step in enumerate(job["steps"]):
        if needle in _step_text(step):
            return index
    raise AssertionError(f"job {job.get('name')!r} 里找不到含 {needle!r} 的步骤")


def _split_port_mapping(mapping: object) -> tuple[int, int]:
    """把 GHA service 的端口映射（``5433:5432`` 或 ``5433:5432/tcp``）拆成 (宿主, 容器)。"""
    host, _, rest = str(mapping).partition(":")
    return int(host), int(rest.split("/")[0])


def _service_host_ports(job: dict) -> dict[int, int]:
    """取 job 的 service 宿主端口 → 容器端口映射。"""
    result: dict[int, int] = {}
    for service in (job.get("services") or {}).values():
        for mapping in service.get("ports") or []:
            host, container = _split_port_mapping(mapping)
            result[host] = container
    return result


def _compose_image(path: Path, service: str) -> str:
    """读 compose 里某服务使用的镜像名。"""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return str(doc["services"][service]["image"])


def _hardcoded_loopback_ports() -> set[int]:
    """扫出 `tests/` 里硬编码为 `127.0.0.1:<port>` 的端口。

    跳过本文件：契约测试自身当然会提到这些端口号，那属于「描述」而不是「连接」，
    算进来只会让断言自我指涉、难以阅读。

    剔除整行注释：注释里的地址是叙述性的（例如「宿主 5433 被另一个 PostgreSQL
    占用」），不代表运行时会去连它。
    """
    ports: set[int] = set()
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if path.name == Path(__file__).name:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            ports.update(int(m) for m in re.findall(r"127\.0\.0\.1:(\d+)", line))
    return ports


def _dockerfile_python_version() -> str:
    """从 Dockerfile 的 `FROM python:X.Y-...` 里取版本号。"""
    match = re.search(r"^FROM\s+python:(\d+\.\d+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    assert match, "Dockerfile 里没找到 `FROM python:<version>`，无法与 CI 交叉校验"
    return match.group(1)


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    doc, _raw = _load_workflow()
    return doc


@pytest.fixture(scope="module")
def workflow_text() -> str:
    _doc, raw = _load_workflow()
    return raw


@pytest.fixture(scope="module")
def jobs(workflow: dict) -> dict:
    return workflow["jobs"]


# ---------------------------------------------------------------------------
# 1. 文件、触发与权限
# ---------------------------------------------------------------------------


def test_workflow_lives_at_the_path_declared_in_the_spec() -> None:
    """§4 的文件清单把 CI 定在 `.github/workflows/ci.yml`，不是别的名字。"""
    assert WORKFLOW.is_file(), f"缺少 {WORKFLOW.relative_to(PROJECT_ROOT)}"


def test_workflow_parses_and_declares_name(workflow: dict) -> None:
    assert workflow.get("name") == "CI"


def test_runs_on_push_and_pull_request_to_master(workflow: dict) -> None:
    """两个触发都要有：只管 push 则 PR 无门禁，只管 PR 则直接推 master 无人拦。"""
    triggers = _triggers(workflow)
    for event in ("push", "pull_request"):
        assert event in triggers, f"缺少触发事件: {event}"
        assert triggers[event]["branches"] == ["master"]


def test_supports_manual_dispatch(workflow: dict) -> None:
    """手动触发：排查偶发失败时不必造一个空提交去触发 CI。"""
    assert "workflow_dispatch" in _triggers(workflow)


def test_does_not_use_pull_request_target(workflow: dict, workflow_text: str) -> None:
    """不得使用 `pull_request_target`。

    该事件在**目标仓库**的上下文里运行（含 secrets），却由外部 PR 的内容触发——
    只要 checkout 了 PR 的代码，就等于把仓库凭据交给任意贡献者。本 workflow 只需要
    `pull_request` 即可。
    """
    assert "pull_request_target" not in _triggers(workflow)
    assert "pull_request_target" not in workflow_text


def test_permissions_are_read_only(workflow: dict) -> None:
    """CI 只读仓库内容：不推送镜像、不写 PR，就不该申请写权限。"""
    assert workflow.get("permissions") == {"contents": "read"}


def test_concurrency_cancels_superseded_runs(workflow: dict) -> None:
    """同一分支推一串提交时，旧 run 应被取消，不必排队等前一个跑完。"""
    concurrency = workflow.get("concurrency")
    assert concurrency, "缺少 concurrency 配置"
    assert concurrency.get("cancel-in-progress") is True
    assert "github.ref" in concurrency.get("group", "")


def test_every_job_has_a_timeout(jobs: dict) -> None:
    """每个 job 都要有 `timeout-minutes`。

    默认上限是 360 分钟：一个卡住的 job（例如等一个永远不就绪的 service）会白占
    六小时。设上限让「卡住」最多浪费十几分钟。
    """
    for name, job in jobs.items():
        assert job.get("timeout-minutes"), f"job {name} 没有设置 timeout-minutes"


# ---------------------------------------------------------------------------
# 2. job 与步骤顺序（§44 四步的落地）
# ---------------------------------------------------------------------------


def test_job_set_matches_the_three_responsibilities(jobs: dict) -> None:
    assert set(jobs) == EXPECTED_JOBS


def test_lint_job_installs_deps_before_linting(jobs: dict) -> None:
    """先装依赖再 lint：没装 ruff 就跑 `ruff check` 会以 127 失败，报错毫无信息量。"""
    lint = jobs["lint"]
    install = _step_index(lint, "requirements-dev.txt")
    check = _step_index(lint, "ruff check")
    assert install < check, "lint job 的安装依赖步骤必须在 ruff check 之前"


def test_test_job_order_is_install_migrations_then_pytest(jobs: dict) -> None:
    """test job 的三段必须按「装依赖 → 迁移 → pytest」排列。

    迁移若排在 pytest 之后（或缺失），用例会跑在一个没有表的库上，失败信息是
    一堆 `UndefinedTableError`，与真实原因（建表没做）隔得很远。
    """
    test_job = jobs["test"]
    install = _step_index(test_job, "requirements-dev.txt")
    migrate = _step_index(test_job, "alembic upgrade head")
    run_tests = _step_index(test_job, "pytest")
    assert install < migrate < run_tests


def test_docker_build_job_builds_the_root_dockerfile(jobs: dict) -> None:
    """docker build 用仓库根的 Dockerfile（不加 `-f` 即默认），tag 显式且非 latest。"""
    build_job = jobs["docker-build"]
    index = _step_index(build_job, "docker build")
    run_line = build_job["steps"][index]["run"]
    assert "taskflow-app:ci" in run_line
    assert "latest" not in run_line


def test_python_version_matches_the_runtime_image(workflow: dict) -> None:
    """CI 的 Python 版本必须与 Dockerfile 的运行时镜像同大版本。

    两处漂移的后果很隐蔽：CI 全绿，而生产镜像里的 Python 是另一个版本，
    语法/标准库行为差异只在部署后才暴露。这里从 Dockerfile 反向读取并比对。
    """
    expected = _dockerfile_python_version()
    assert workflow["env"]["PYTHON_VERSION"] == expected, (
        f"CI 用 Python {workflow['env']['PYTHON_VERSION']}，"
        f"而 Dockerfile 用 python:{expected}——两者必须一致"
    )
    for name in ("lint", "test"):
        for step in _jobs_of(workflow, name)["steps"]:
            if str(step.get("uses", "")).startswith("actions/setup-python"):
                assert step["with"]["python-version"] == "${{ env.PYTHON_VERSION }}"


def test_python_jobs_install_the_dev_requirements(workflow: dict) -> None:
    """lint 与 test 都装 `requirements-dev.txt`（它内部 `-r requirements.txt`）。

    若某处写成只装 `requirements.txt`，lint job 会因为没有 ruff 而失败，或者
    测试会漏装依赖——两者的修法都比「一开始就装对」麻烦。
    """
    for name in ("lint", "test"):
        text = "\n".join(_step_text(step) for step in _jobs_of(workflow, name)["steps"])
        assert "requirements-dev.txt" in text, f"{name} job 没有装 requirements-dev.txt"


# ---------------------------------------------------------------------------
# 3. Lint 的可复现性
# ---------------------------------------------------------------------------


def test_ruff_version_is_pinned() -> None:
    """ruff 版本必须用 `==` 钉死。

    用 `>=` 的话，「这次提交能不能过 lint」取决于 CI 当天装到哪个版本——同一份
    提交会时红时绿，而重跑一次就好了的现象会让人彻底不再信任 lint 门禁。
    """
    text = REQUIREMENTS_DEV.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    pins = [line for line in lines if line.startswith("ruff")]
    assert len(pins) == 1, f"requirements-dev.txt 里应当恰好有一行 ruff 依赖，实际: {pins}"
    assert re.fullmatch(r"ruff==\d+\.\d+\.\d+", pins[0]), f"ruff 必须钉死版本，实际: {pins[0]}"


def test_dev_requirements_extend_the_runtime_requirements() -> None:
    """dev 依赖应 `-r requirements.txt`，而不是把运行时依赖再抄一遍。"""
    lines = [line.strip() for line in REQUIREMENTS_DEV.read_text(encoding="utf-8").splitlines()]
    assert "-r requirements.txt" in lines


def test_ruff_is_not_a_runtime_dependency() -> None:
    """ruff 不得出现在 `requirements.txt`。

    该文件被 Dockerfile 用于生产镜像；把 lint 工具装进去既是纯死重量，也让
    「生产镜像里装了什么」这件事无法单独审计。
    """
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert not re.search(r"^\s*ruff", text, re.M), "生产依赖里出现了 ruff"


def test_ruff_rule_set_is_declared_explicitly() -> None:
    """`[tool.ruff.lint] select` 必须显式声明。

    实测（ruff 0.16.7）：同一份代码不写 `select` 会报 219 项，写成本仓库的规则集
    则报 36 项。依赖默认值等于把 lint 通过与否交给 ruff 的版本决定，因此规则集
    要像版本一样钉在仓库里。
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    ruff = config["tool"]["ruff"]
    assert ruff["target-version"] == "py313"
    assert ruff["lint"]["select"] == ["E4", "E7", "E9", "F"]


# ---------------------------------------------------------------------------
# 4. service 端口契约（本 TASK 最要紧的一组断言）
# ---------------------------------------------------------------------------


def test_services_match_the_images_used_by_compose(jobs: dict) -> None:
    """CI 的 service 镜像与 compose 里的**同名同 tag**。

    端口与镜像版本都一致时，「本地 compose 通过 / CI 挂掉」这种差异才只剩
    「谁来提供 Postgres」这一条，排查面小得多。
    """
    services = jobs["test"]["services"]
    assert services["postgres"]["image"] == _compose_image(DEV_COMPOSE, "postgres")
    assert services["redis"]["image"] == _compose_image(DEV_COMPOSE, "redis")
    # 生产 compose 用的是同一组官方镜像 tag（见 test_prod_compose.py 的说明）。
    assert services["postgres"]["image"] == _compose_image(PROD_COMPOSE, "postgres")
    assert services["redis"]["image"] == _compose_image(PROD_COMPOSE, "redis")


def test_service_ports_cover_the_ports_hardcoded_in_tests(jobs: dict) -> None:
    """**核心断言**：测试写死的每个后端端口，CI 都要有 service 监听它。

    测试里是 `127.0.0.1:5433` / `127.0.0.1:6389` 这样的模块级常量（历史原因：
    本机 5432 被另一个 PostgreSQL 占用）。CI 把 service 端口映射成同样的值，
    而不是反过来改 40 个测试文件——后者的代价与风险见文件的模块 docstring。
    """
    host_ports = _service_host_ports(jobs["test"])
    missing = set(REQUIRED_SERVICE_PORTS) - set(host_ports)
    assert not missing, f"CI 未映射测试需要的端口: {sorted(missing)}"


def test_service_port_mappings_are_the_expected_container_ports(jobs: dict) -> None:
    """宿主端口 → 容器内端口的一一对应也要对：5433→5432、6389→6379。

    只对宿主端口做断言的话，「把 5433 映射到 redis 的 6379」这种错位仍会通过。
    """
    host_ports = _service_host_ports(jobs["test"])
    expected = {5433: 5432, 6389: 6379}
    assert host_ports == expected, f"端口映射应为 {expected}，实际 {host_ports}"


def test_no_service_is_provided_without_a_test_using_it(jobs: dict) -> None:
    """反向断言：CI 不该提供测试用不到的服务端口。

    防止有人「反正加上无害」地映射一个 MySQL / 额外 Redis，让 CI 白等一次启动。
    新增端口时应当先有测试在用它。
    """
    host_ports = set(_service_host_ports(jobs["test"]))
    assert host_ports == set(REQUIRED_SERVICE_PORTS)


def test_required_service_ports_are_actually_used_by_tests() -> None:
    """`REQUIRED_SERVICE_PORTS` 自身也不能腐坏。

    若将来测试改成从配置读地址（不再硬编码），这份「必需端口」清单就成了过期的
    臆测。这里反向确认清单里的每个端口在 `tests/` 里确有引用。
    """
    used = _hardcoded_loopback_ports()
    for port in REQUIRED_SERVICE_PORTS:
        assert port in used, f"REQUIRED_SERVICE_PORTS 里的 {port} 已无测试引用，清单需要更新"


def test_hardcoded_ports_are_all_accounted_for() -> None:
    """`tests/` 里出现的端口，要么需要服务、要么在已知例外清单里。

    这是「防漂移」：将来有人写测试时引用了第三个端口（比如换一个 Redis 实例或加
    MySQL），CI 会红，逼他明确决定「是给 CI 加 service，还是把它记为刻意关闭的
    探测端口」——而不是让 CI 在后台悄悄连着失败。
    """
    unexplained = _hardcoded_loopback_ports() - set(REQUIRED_SERVICE_PORTS) - set(
        KNOWN_NON_SERVICE_PORTS
    )
    assert not unexplained, (
        f"tests/ 里出现了未被 CI 覆盖、也未登记的端口: {sorted(unexplained)}；"
        "要么在 workflow 的 service 里提供它，要么加入 KNOWN_NON_SERVICE_PORTS 并写明原因"
    )


def test_known_exceptions_do_not_shadow_required_ports() -> None:
    """例外清单不得与「必需端口」重叠。

    重叠就等于用一个「无需服务」的标签悄悄豁免了必需端口，让核心断言失效。
    """
    overlap = set(KNOWN_NON_SERVICE_PORTS) & set(REQUIRED_SERVICE_PORTS)
    assert not overlap, f"这些端口同时出现在必需与例外清单里: {sorted(overlap)}"


def test_services_have_health_checks(jobs: dict) -> None:
    """service 必须有健康检查。

    没有 health check 时，容器一起来（进程还没能接受连接）workflow 就继续往下跑，
    安装依赖的几十秒**通常**够 Postgres 就绪——于是这变成一个「多数时候能过」的
    偶发失败。health check 把这种不确定性去掉。
    """
    for name, service in jobs["test"]["services"].items():
        options = str(service.get("options") or "")
        assert "--health-cmd" in options, f"service {name} 缺少 --health-cmd"
        assert "--health-retries" in options, f"service {name} 缺少 --health-retries"


def test_backend_urls_agree_with_service_ports(jobs: dict) -> None:
    """`DATABASE_URL` / `REDIS_URL` 里的端口要与 service 映射一致。

    这两处是同一件事的两种写法（一处给容器映射，一处给应用连接），漂移后行为是
    「宿主机端口映射对了，但应用连了另一个端口」，症状与「service 没起来」几乎一样。
    """
    host_ports = _service_host_ports(jobs["test"])
    env = jobs["test"]["env"]
    for variable, port in (("DATABASE_URL", 5433), ("REDIS_URL", 6389)):
        assert port in host_ports, f"{variable} 引用的 {port} 不在 service 映射里"
        assert f":{port}/" in env[variable], f"{variable} 未指向 127.0.0.1:{port}，实际: {env[variable]}"


def test_database_url_uses_the_async_driver(jobs: dict) -> None:
    """`DATABASE_URL` 必须是 `postgresql+asyncpg://`。

    应用是异步 SQLAlchemy；写成同步的 `postgresql://` 会在创建引擎时失败，报错
    信息和「连接串写错」相差很远（alembic 与 pytest 都会一起炸）。
    """
    url = jobs["test"]["env"]["DATABASE_URL"]
    assert url.startswith("postgresql+asyncpg://"), url


def test_secrets_are_clearly_ci_only(workflow_text: str) -> None:
    """CI 里不得出现任何真实凭据的痕迹。

    流水线里出现的密码只应是测试用的弱值（postgres/postgres）。这里做一次粗筛：
    出现 `change-me` 之外的「看起来像密钥」的赋值就值得人看一眼。
    """
    assert "JWT_SECRET_KEY" in workflow_text
    # 明确标注这是 CI 专用占位值，避免有人误以为它与任何环境共享。
    assert "not-a-real-secret" in workflow_text
    assert "4ad958638c2c3f78441bd14623e36b4a97977fb2dfb035407a447cf858419400" not in workflow_text


# ---------------------------------------------------------------------------
# 5. 配置等价性：CI 与本地只应差「谁提供 Postgres / Redis」
# ---------------------------------------------------------------------------


def test_ci_env_keys_are_real_settings_fields(jobs: dict) -> None:
    """传给 job 的每个环境变量名都必须是真实的 Settings 字段。

    拼错名字（例如 `DATABSE_URL`）不会报错，只会静默按默认值运行——于是 CI 连的是
    `postgres:5432`，失败信息看起来像「service 没起来」。这类「配置不生效」最难发现，
    故用 Settings 的字段清单做交叉校验（与 test_prod_compose.py 对 compose 的做法一致）。
    """
    known = {field.upper() for field in Settings.model_fields}
    for key in jobs["test"]["env"]:
        assert key.upper() in known, f"CI 传了未知环境变量: {key}"


def test_ci_env_is_exactly_the_unusable_defaults(jobs: dict) -> None:
    """CI 的环境变量集合恰好是那三个「默认值在本环境不可用」的配置项。

    逐条对应：
      - `DATABASE_URL` / `REDIS_URL`：默认值是 compose 网络里的服务名
        （`postgres:5432` / `redis:6379`），GitHub runner 上无法解析；
      - `JWT_SECRET_KEY`：默认值是 `change-me`，覆盖它只为让 CI 与本地一致。

    断言「恰好」而不只是「包含」：多出来的键（比如顺手加个 `APP_ENV=production`）
    会引入第三种配置，让「CI 绿 ⇒ 本地绿」这条性质悄悄失效。
    """
    assert set(jobs["test"]["env"]) == {"DATABASE_URL", "REDIS_URL", "JWT_SECRET_KEY"}


def test_ci_overrides_the_container_hostname_defaults(jobs: dict) -> None:
    """设了的连接串必须**真的改掉**默认值里的容器服务名。

    若有人把 `DATABASE_URL` 又写成 `postgres:5432`（从 compose 那边抄过来），
    这个变量就形同虚设——端口断言会通过，而用例依然连不上任何东西。
    """
    env = jobs["test"]["env"]
    assert "postgres:5432" not in env["DATABASE_URL"]
    assert "redis:6379" not in env["REDIS_URL"]
    assert "127.0.0.1" in env["DATABASE_URL"]
    assert "127.0.0.1" in env["REDIS_URL"]


# ---------------------------------------------------------------------------
# 6. 迁移可逆性（§37）
# ---------------------------------------------------------------------------


def test_migration_step_runs_upgrade_downgrade_upgrade(jobs: dict) -> None:
    """三步命令与顺序：`upgrade head` → `downgrade base` → `upgrade head`。

    中间必须有 `downgrade base`：这正是 §37 想要的「migration test」。缺了它，本
    步骤就退化成「建表」，那件事 pytest 本来也会暴露。
    """
    test_job = jobs["test"]
    index = _step_index(test_job, "alembic upgrade head")
    run = str(test_job["steps"][index]["run"])
    commands = [line.strip() for line in run.splitlines() if "alembic" in line]
    assert commands == [
        "alembic upgrade head",
        "alembic downgrade base",
        "alembic upgrade head",
    ], f"迁移步骤的命令与顺序不符: {commands}"


def test_migration_step_fails_fast(jobs: dict) -> None:
    """三步写在**同一条** shell 里并 `set -e`。

    若拆成三个 step，GHA 固然也会在失败处停下；但写成一条 `run` 时如果漏了
    `set -e`（或依赖默认行为），失败可能被吞掉，后续步骤在旧库上继续，最终呈现出
    「pytest 通过」的假绿。
    """
    test_job = jobs["test"]
    index = _step_index(test_job, "alembic upgrade head")
    run = str(test_job["steps"][index]["run"])
    assert "set -euo pipefail" in run


# ---------------------------------------------------------------------------
# 7. 不推送镜像
# ---------------------------------------------------------------------------


def test_pipeline_publishes_nothing(workflow_text: str) -> None:
    """本 TASK 的 CI 只做验证，不发布镜像。

    推送需要 `packages:write` 权限与 registry 凭据。一个纯粹用来回答「能不能构建」
    的步骤不该带上这把钥匙；真需要发布时应是独立的发布 workflow（带环境审批）。
    """
    forbidden = ("docker push", "docker/login-action", "ghcr.io", "packages: write")
    for needle in forbidden:
        assert needle not in workflow_text, f"CI 不应包含发布相关的内容: {needle}"
