# 命令集设计

## 初始化 workspace

- 命令格式
  - `yzrws init`
- 命令具体说明

1. 创建 workspace 的目录，按照 `README.md` 规定创建目录结构
2. 若 workspace 的目录已存在，则进行自检逻辑，检查 workspace 的目录元数据是否完整

## 创建 workitem

- 命令格式
  - `yzrws create workitem <workitem_name>`
- 命令具体说明

1. 创建一个 workitem，名字用 `workitem_name`；如果已存在，回显当前 workitem 已存在
2. 若 workitem 不存在，则进入创建流程；在 workspace 目录下创建对应的同名子目录

## 列举 workitem

- 命令格式
  - `yzrws list`
- 命令具体说明

1. 列举当前已存在的 workitem

## 导入 workitem

- 命令格式
  - `yzrws import <workitem_name>`
