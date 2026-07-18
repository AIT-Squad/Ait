<!-- @id:[FSD]-ait-version -->
## version 内部分解

### 功能描述
version 域的实现分解。该域负责版本生命周期与基线合并:版本是全有或全无的原子变更单元——chunk 三态流转(working 可改 → staged 中间态 → committed 锁定)、锁定后过纯门禁(可重复跑、不落盘的校验报告)、原子合入基线(一次 git 提交,失败按字节回退不残留半合入状态)、任意阶段整版退出。实现拆为两个文件:version_manager(生命周期编排)与 merge_engine(chunk 级合并算法)。

### 反向要求
- 不解析 chunk 语法(归 doc_model 域)、不存储关系图(归 specgraph 域)、不生成制品(归 new_model 域)。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 version 域块,本文件是内部实现分解)。

### 分解视图
- version_manager 叶(details → [TDD]-version_manager):VersionManager 类,生命周期编排
- merge_engine 叶(details → [TDD]-merge_engine):纯 chunk 级合并算法

<!-- @id:[FSD]-ait-version:version_manager -->
## version_manager
### 功能描述
VersionManager 类,版本全生命周期的编排者。职责:版本元数据与索引的创建读写;chunk 三态流转与 commit 锁定(锁定后修改报错,uncommit 可把 committed/staged 打回 working 作层级返工);纯门禁 gate——汇集 task 完成度、重复/改名冲突、六不变式(①PRD↔1FSD ②TDD↑1FSD↓1制品 ③制品↔1TDD ④关联经真实 chunk ⑤无孤儿 ⑥制品可追溯到 PRD)与制品验收(配置的测试命令)的校验报告,可重复跑、零落盘;原子 confirm——同一套门禁前置,通过后备份 docs 与 .meta 关键状态、逐文件合并 chunk、提升关系图入基线、git 提交,任一步失败按字节还原并报 MERGE_ROLLBACK,成功则版本标记 merged;reset 物理清空未合入版本。git 提交三分语义:非 git 环境容忍(结果标 git:"unavailable")、无变更时返回当前 HEAD、真实失败进回滚路径(不伪装成功)。

- **v2.55 GIT_DIRTY 去除**:版本生命周期内 docs 仓故意 dirty,confirm 不再预检 git 状态;`_git_clean()` 保留但 confirm 不调用(留作诊断工具)。
- **v2.55 merge 绑定字段**:merge 成功后将 `_git_commit` 返回的 sha 写入 meta.docs_commit;以只读方式调 `git rev-parse HEAD cwd=root.parent` 取宿主 HEAD 写入 meta.code_base(守红线:只读不写宿主;宿主非 git 仓时 code_base=None)。

### 反向要求
- 不做 chunk 内容合并的具体算法(委托 merge_engine)。
- 不校验 chunk 语法(委托 doc_model 域的解析器)、不计算六不变式细节(委托 new_model 域的校验器,本类只编排调用与拒绝)。
- 不直接被其它域实例化用于合并以外的用途(其它域经域契约使用)。

<!-- @id:[FSD]-ait-version:merge_engine -->
## merge_engine
### 功能描述
纯 chunk 级合并算法,version 域内部件(仅被 version_manager 的 confirm 调用,不对其它域暴露)。接口:`merge_file(base:ParsedFile, ops:list[VersionChunkOp]) -> MergedFile`、`merge_new_file(file, ops) -> MergedFile`、`serialize(file_header, chunks) -> str`。语义:按 baseline 真实存在性逐 chunk 处理——modify=整块全替换(version 侧须自带完整最终内容)、modify 目标不在 baseline 则当 add 追加、add 撞已存在报错——绝不静默丢 chunk。

### 反向要求
- 不读写磁盘(纯内存转换,落盘由 version_manager 负责)。
- 不做冲突策略决策(hash 冲突的取舍由调用方传入)。
- 不处理关系图(specgraph 的提升由 version_manager 编排)。

<!-- @id:[FSD]-ait-version:TEST -->
## TEST 集成验收
version 域所有部件(version_manager + merge_engine)合并到一起、作为整体的集成验收:
1. WHEN 含 committed chunk 的合规版本 gate 通过(六不变式零违例——无孤儿/无断链/无制品撞车/无幽灵边/基数约束全满足,且制品验收测试绿)→ confirm THEN baseline 原子更新 + 一次 git commit,version 标 merged,返回 merged_chunks 与 commit。
2. IF confirm 任一步失败(关系图提升 / git 提交真实失败)THEN docs 与 .meta 关键状态按字节还原(MERGE_ROLLBACK),merged 标记不残留、快照目录清除,回退后可直接重试。
3. IF 版本违反六不变式任一条 THEN gate passed=false 并列出违例明细,confirm 报 INVARIANT_VIOLATION 拒于任何落盘之前。
4. IF 配置了验收命令且测试红 THEN confirm 报 ACCEPTANCE_FAILED 拒于落盘之前;未配置则跳过(不影响 legacy 项目)。
5. merge_engine:整块 modify 替换后不丢兄弟 chunk、modify 目标不在 baseline 当 add 追加、add 撞已存在 baseline id 报 DUPLICATE_BASELINE_CHUNK。
6. 非 git 环境 confirm 成功但结果标 git:"unavailable"(不伪装提交)。
7. WHEN merge 成功 THEN meta.docs_commit 为 docs 仓 commit sha;meta.code_base 为宿主 HEAD(或 None 若宿主非 git 仓);merge 后 docs 仓 `git status` 干净。
8. WHEN 版本进行中 confirm THEN 不因 docs 仓 dirty 失败(GIT_DIRTY 预检已去除)。

