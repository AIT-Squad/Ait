<!-- @id:[FSD]-ait-version -->
## version 内部分解

### 功能描述
version 域的实现分解(承接域契约 [FSD]-ait:version)。拆为编排(version_manager)与合并算法(merge_engine)两个文件。

### 分解视图
- version_manager 叶(details → [TDD]-version_manager):VersionManager 类,编排全生命周期
- merge_engine 叶(details → [TDD]-merge_engine):纯 chunk 级合并算法

<!-- @id:[FSD]-ait-version:version_manager -->
## version_manager
### 功能描述
VersionManager 类,编排版本全生命周期:三态流转、commit 锁定、uncommit 层级返工、纯门禁 gate(可重复零落盘)、原子 confirm(precheck〔task/git/去重/override 冲突/六不变式/制品验收〕→backup→merge→specgraph 提升→git commit,失败字节级回退)、reset 物理删除。域契约的主要实现者;完整接口见域契约 [FSD]-ait:version,文件级实现设计详见 [TDD]-version_manager。

<!-- @id:[FSD]-ait-version:merge_engine -->
## merge_engine
### 功能描述
纯 chunk 级合并算法,version 域内部件(仅被 version_manager 的 confirm 调用,不对其它域暴露)。接口:`merge_file(base:ParsedFile, ops:list[VersionChunkOp]) -> MergedFile`、`merge_new_file(file, ops) -> MergedFile`、`serialize(file_header, chunks) -> str`。语义:按 baseline 真实存在性逐 chunk 处理——modify=整块全替换、目标不在 baseline 当 add、add 撞已存在报错——绝不丢 chunk。详见 [TDD]-merge_engine。

<!-- @id:[FSD]-ait-version:TEST -->
## TEST 集成验收
version 域所有部件(version_manager + merge_engine)合并到一起、作为整体的集成验收:
1. WHEN 含 committed chunk 的合规版本 gate 通过(六不变式+验收绿)→ confirm THEN baseline 原子更新 + 一次 git commit,version 标 merged,返回 merged_chunks 与 commit。
2. IF confirm 任一步失败(specgraph 提升 / git commit 真实失败)THEN docs 与 .meta 关键状态字节级回退(MERGE_ROLLBACK),merged 标记不残留、快照目录清除,回退后可直接重试。
3. IF 版本违反六不变式(孤儿/断链/制品撞车/树关系环)THEN gate passed=false、confirm 报 INVARIANT_VIOLATION 拒于任何落盘之前。
4. IF 配置了 acceptance_command 且测试红 THEN confirm 报 ACCEPTANCE_FAILED 拒于落盘之前;未配置则跳过(vacuous)。
5. merge_engine:整块 modify 替换后不丢兄弟 chunk、modify 目标不在 baseline 当 add 追加、add 撞已存在 baseline id 报 DUPLICATE_BASELINE_CHUNK。
6. 非 git 环境 confirm 成功但结果标 git:"unavailable"(不伪装 commit)。
