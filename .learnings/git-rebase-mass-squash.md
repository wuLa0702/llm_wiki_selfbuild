# Git 批量 Rebase 合并提交经验

## 场景
将 32 个零散提交（含大量紧耦合的 fixup/feat 交替提交）合并为 12 个逻辑清晰的提交，同时将英文提交注释改成中文。

## 关键要点

### 1. 前置准备
- **备份当前 HEAD**: `git branch backup-pre-rebase HEAD`（确保出问题能回退）
- **处理 untracked 文件**: 如果某些提交要删除的目录（如 `.specify/`）当前是 untracked 状态，rebase 会遇到 `untracked working tree files would be overwritten` 错误。解决方法：临时 `mv .specify /tmp/.specify-backup`
- **Stash 工作区改动**: `git stash push -m "pre-rebase stash"` 避免 rebase 被 unstaged changes 阻挡

### 2. Rebase Todo 编写技巧
使用 `GIT_SEQUENCE_EDITOR` 环境变量自动注入 todo 文件，避免在编辑器内手动操作：

```bash
GIT_SEQUENCE_EDITOR="cp /tmp/rebase-todo.txt" git rebase -i <base-commit>
```

**Todo 文件中避免中文**：`pick` 行后的注释如果包含中文，某些 git 版本会报 `invalid line` 错误。解决方案：

```
# ❌ 不要这样（git 可能报错）
pick abc1234 特性: 中文注释

# ✅ 用 ASCII 写临时注释，用 exec 改中文消息
pick abc1234 feat: english description
exec git commit --amend -m "特性: 中文消息" --allow-empty
```

### 3. 使用 `fixup + exec` 代替 `squash` 或 `reword`

```
# 推荐方案：fixup 合并 + exec 改消息
pick abc1234 First commit       # 承接收起
fixup def5678 Fix something      # 无声合并
fixup 789abcd Another fix        # 无声合并
exec git commit --amend -m "统一的中文消息" --allow-empty
```

相比于 `squash` （打开编辑器合并消息）或 `reword` （打开编辑器改消息），`fixup + exec` 完全自动化，不需要手动处理编辑器交互。

注意 `--allow-empty` 参数：exec 运行 `git commit --amend` 时，如果上次 fixup 没有产生文件变更，不加此参数会失败。

### 4. 冲突处理策略

大规模 squash 时，同文件的连续提交必然产生冲突。关键在于：

**同组 squash 内的冲突 → 取 incoming（后者）版本**：
由于 `fixup` 是将后续提交合并到前一个提交中，冲突是前者（HEAD）和后者的差异。后者是修复前者的，所以取后者是正确的。

用 Python 脚本自动化冲突解决：

```python
with open(fname, 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    stripped = lines[i].strip()
    if stripped == '<<<<<<< HEAD':
        i += 1
        while i < len(lines) and lines[i].strip() != '=======':
            i += 1
        i += 1  # skip =======
        while i < len(lines) and not lines[i].strip().startswith('>>>>>>> '):
            new_lines.append(lines[i])  # keep incoming
            i += 1
        i += 1  # skip >>>>>>>
    else:
        new_lines.append(lines[i])
        i += 1
```

**核心原则**：在同一 squash 组内，永远取 incoming（后者的修改），因为后者是以前者为基础做的修复。

### 5. 分组策略

合并提交的分组原则：
- **同文件连续修改**：如 `graph.html` 被连续 8 个提交修改 → 合并
- **功能特征高度耦合**：如多个 CSS/布局修复交替出现 → 合并为一次"布局修复"
- **有明确阶段标识的**：如 `Phase 6 batch1/2/3/4` → 保留阶段边界，合并内部子提交
- **跨文件的附带改动**：如 `purpose.md` 迁移 + `.specify/` 清理 + 模板修改 → 归入"布局修复与重构"
- **避免合并粒度太粗**：不超过 6 个子提交合并为一个，否则丢失历史追溯能力

### 6. 最终效果

| 指标 | 值 |
|------|-----|
| 原始提交数 | 32 |
| 合并后提交数 | 12 |
| 精简比例 | 62.5% |
| Git 命令 | `git rebase -i + GIT_SEQUENCE_EDITOR` |
| 冲突次数 | 5 次（全是同组 squash 内的文件冲突） |
| 是否需要人工干预编辑器 | 否（全程自动化） |
