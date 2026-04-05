首次启动：

```
docker build -t my_agent_env:latest .  #给agent提供沙盒环境，工作目录映射为agent_vm
conda env create -f environment.yml
conda activate CatInCup
```
