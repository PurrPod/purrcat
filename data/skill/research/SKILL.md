---
name: research
description: 复现论文专用工作流，当且仅当老板要求复现某论文时使用
---

查看论文pdf可以用filesysytem的parse_document工具

首先在沙盒里运行git clone，看github仓库，检测论文同款数据集、预处理、训练脚本、推理脚本、评估脚本是否齐全，列成markdown表格。

其次看如何配置环境，列出命令行清单，要精确版本号。（如果没有conda要先安装miniconda，单独开一个虚拟环境，防止污染环境）

然后扫描论文pdf，检测其中的评估指标是什么，复现出来的结果应该包含什么，数值大致范围是什么，列成markdown表格。

然后按照标准流程复现，遇到问题要记录到problem.txt里，并记录最终是如何解决的。