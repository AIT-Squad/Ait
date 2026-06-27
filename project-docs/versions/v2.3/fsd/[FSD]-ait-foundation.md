<!-- @id:[FSD]-ait-foundation -->
## foundation FSD

<!-- @summary: 通用工具基础设施域。details 到对应 TDD（一文件一映射）。 -->

### 功能范围

项目根解析、原子写、YAML 存取、哈希。

<!-- @id:[FSD]-ait-foundation:root -->
## root

<!-- @summary: 项目根解析：定位含 project-docs 的根、CWD 校验（NOT_AT_PROJECT_ROOT / CWD_INSIDE_PROJECT_DOCS）。 details [TDD]-root。 -->

### 功能描述

项目根解析：定位含 project-docs 的根、CWD 校验（NOT_AT_PROJECT_ROOT / CWD_INSIDE_PROJECT_DOCS）。

<!-- @id:[FSD]-ait-foundation:io_utils -->
## io_utils

<!-- @summary: atomic_write_text：原子写文件（临时文件 + 替换）。 details [TDD]-io_utils。 -->

### 功能描述

atomic_write_text：原子写文件（临时文件 + 替换）。

<!-- @id:[FSD]-ait-foundation:yaml_io -->
## yaml_io

<!-- @summary: save_model/load_model：pydantic 模型 ↔ YAML 文件存取。 details [TDD]-yaml_io。 -->

### 功能描述

save_model/load_model：pydantic 模型 ↔ YAML 文件存取。

<!-- @id:[FSD]-ait-foundation:hash_utils -->
## hash_utils

<!-- @summary: chunk_hash：chunk 内容哈希（用于 base_hash 失效检测）。 details [TDD]-hash_utils。 -->

### 功能描述

chunk_hash：chunk 内容哈希（用于 base_hash 失效检测）。
