<!-- @id:[FSD]-ait-state -->
## state FSD
### 功能范围
版本进度面板渲染与保存：三态分布、impl 覆盖、task 状态、phase/title。
### 交互契约
`render_state(version, fmt) / save_state(version)`；`load_version_state -> StatePanel`。

<!-- @id:[FSD]-ait-state:state -->
## state
### 功能描述
load_version_state 汇总(三态/impl 覆盖 compute_impl_coverage/task)→ StatePanel；render_markdown/json；save_state 写 versions/<v>/state.md。详见 [TDD]-state。
