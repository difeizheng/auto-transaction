---
name: 回测脚本偏好
description: 回测测试脚本使用 ASCII 字符而非中文/emoji，避免 Windows GBK 编码问题
type: feedback
---

**规则**：创建或修改回测测试脚本时，使用 ASCII 字符输出，避免中文和 emoji。

**Why**：Windows GBK 编码环境下，emoji 和中文字符会导致 `UnicodeEncodeError: 'gbk' codec can't encode character` 错误，影响脚本执行。

**How to apply**：
- 脚本中的 print 输出使用英文或纯 ASCII 字符
- 表格、分隔线使用 ASCII 符号 (=, -, |)
- 日志文件中的中文内容需注意编码问题
