<!-- @id:[FSD]-ait-init -->
## init 内部分解

### 功能描述
init 域的实现分解。该域负责 `ait init` 项目初始化:把一个空目录或既有项目引导为 AIT 可管理的项目——生成 project-docs 骨架、写项目本地 wrapper 与 .meta/config.yaml、并按当前状态选择全量 bootstrap 或增量补全。支持两种基线形态:legacy global 基线(overview/tech-stack 等静态 global chunk),与新模型骨架(--new-model:生成 docs/{prd,fsd,tdd} 与 [PRD]/[FSD] 根 + 二者间的 decomposes 边)。幂等——已存在的文件不覆盖,重跑只补缺失项。实现为单文件 init_manager。

### 反向要求
- 不做后续的 PRD/FSD/TDD 内容创作(init 只搭骨架,内容创作归 prd/fsd/tdd 各域的 create 流)。
- 不校验六不变式、不建业务关系边(除 bootstrap 时 PRD→FSD 的初始 decomposes 边);关系维护归 specgraph/new_model 域。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 init 域块,本文件是内部实现分解)。

### 分解视图
- init_manager 叶(details → [TDD]-init_manager):InitManager 类,项目初始化的全部逻辑

<!-- @id:[FSD]-ait-init:init_manager -->
## init_manager
### 功能描述
InitManager 类,`ait init` 的实现者。提供:`run(*, check_only=False, skip=(), new_model=False, project_name="project") -> InitResult`——初始化主入口,先按当前 global 状态判定(fresh 全新 / incomplete 部分存在 / ready 已就绪)选择全量 bootstrap 或增量补全,new_model=True 时改走新模型骨架 bootstrap(生成 [PRD]-{project_name} 与 [FSD]-{project_name} 根,建二者的 decomposes 边入 specgraph),check_only=True 只报告状态不写盘,skip 列出用户声明放弃的增量项;`refresh_wrapper() -> InitResult`——仅重写项目本地 wrapper(路径变更后用);`has_any_version() -> bool`。project_name 经校验(非法字符/路径穿越报 INVALID_PROJECT_NAME);bootstrap 后断言根 chunk 确实进入基线,否则报 BOOTSTRAP_FAILED(防静默产出空基线)。返回 InitResult(created_files, chunks, specs, skill_dir, cli_path, wrapper_path, status, files, skipped)。

- **`_ensure_docs_git_repo()(v2.55)`**:在 `_ensure_project_docs_skeleton` 之后调用;若 `project-docs/.git` 不存在则执行 `git init`(cwd=project-docs);在宿主根 `.gitignore` 安全追加 `project-docs/` 行(先检查是否已存在,exist-check 后追加,不重复);在 `project-docs/.gitignore` 写入 `versions/*/state.md`(派生产物,不追踪)。全部幂等。

### 反向要求
- 不接受工作根覆盖配置(project-docs 位置的硬约束归 foundation 的 root 模块)。
- 不做增量之外的内容修改(不改已存在文件,幂等保证)。
- 不生成 wrapper 以外的可执行脚本、不装依赖(环境准备归安装器 install.py,不在本域)。

<!-- @id:[FSD]-ait-init:TEST -->
## TEST 集成验收
init 域(init_manager)作为整体的集成验收:
1. WHEN 在空的合法项目根跑 `run(new_model=True, project_name="demo")` THEN 生成 docs/{prd,fsd,tdd} 骨架、[PRD]-demo 与 [FSD]-demo 根 chunk 进入基线、二者间 decomposes 边入 specgraph,返回 InitResult 且 chunks>0。
2. WHEN 对已初始化项目重跑 init THEN 幂等——已存在文件不被覆盖,只补缺失项;check_only=True 时只报告 status 不写盘。
3. IF project_name 含非法字符或路径穿越(如 `../x`)THEN 报 INVALID_PROJECT_NAME,不产出任何文件。
4. IF bootstrap 后根 chunk 未能进入基线 THEN 报 BOOTSTRAP_FAILED(不返回静默成功的空基线)。
5. WHEN refresh_wrapper() THEN 仅重写项目本地 wrapper,不动 docs 与基线。
6. WHEN init 完成 THEN project-docs/.git 存在(独立 docs 仓);宿主根 .gitignore 含 project-docs/ 行;project-docs/.gitignore 含 versions/*/state.md。重跑 init 幂等,不重复追加。
