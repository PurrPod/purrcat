---
name:单账户下的子任务并发承压测试、KV cache 命中率测试
description:6个不同agent任务并行完整跑完，实验开始前，确保agent_vm/没有残留测试文件、checkpoint.json也是空的，配置多个模型和api-key（6个），一次跑完，不要reload
result:查看 KV cache 缓存命中率、系统稳定性（超时与否）
---

### prompt

在沙盒环境里创建一个 `/agent_vm/test` 文件夹。
派发给小弟如下任务，让他们在这个文件夹内交付成果：
1. 帮我开发一个英语口译练习的demo网站
2. 帮我整理出一份信号与系统考试复习笔记，涵盖所有关键知识点，数学公式用markdown里的Latex表示（如：$\alpha$）
3. 使用remotion技能编写一个介绍RAG技术的20秒demo remotion动画
4. 用 Github MCP 搜一下飞书 CLI，说说这个仓库里有什么skill，都是干嘛用的？
5. 整理今天力扣每日一题的题目和答案，总结知识点后交付给我
6. 用playwright mcp打开浏览器，访问东方财富网，看看能否正常访问，如果网络出错也没关系，可以直接交付成果

