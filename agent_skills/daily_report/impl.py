"""
Daily Report Skill Implementation
根据 git 历史生成格式化的工作日报
"""

import subprocess
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import re


def run_git_command(repo_path: str, command: List[str]) -> str:
    """
    执行 git 命令并返回结果

    Args:
        repo_path: git 仓库路径
        command: git 命令列表，如 ['log', '--oneline']

    Returns:
        命令输出字符串
    """
    try:
        result = subprocess.run(
            ['git'] + command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        return result.stdout
    except Exception as e:
        return f"Error running git command: {e}"


def get_repo_path(path: str = ".") -> str:
    """
    获取 git 仓库根目录路径

    Args:
        path: 起始路径

    Returns:
        git 仓库根目录绝对路径
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=path,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result.stdout.strip() if result.returncode == 0 else os.path.abspath(path)
    except:
        return os.path.abspath(path)


def analyze_commits(
    repo_path: str = ".",
    since: Optional[str] = None,
    until: Optional[str] = None,
    author: Optional[str] = None,
    max_count: int = 100
) -> Dict[str, Any]:
    """
    分析指定时间范围内的 git 提交记录

    Args:
        repo_path: git 仓库路径
        since: 起始日期，如 "2024-01-01" 或相对时间 "yesterday"
        until: 结束日期
        author: 作者筛选
        max_count: 最大提交数

    Returns:
        包含提交信息的字典

    格式:
    {
        "commits": [
            {
                "hash": "abc123",
                "date": "2024-01-01",
                "author": "name",
                "message": "commit message",
                "files": ["file1.py", "file2.py"],
                "stats": {"additions": 100, "deletions": 50}
            }
        ],
        "total": 10
    }
    """
    # 构建命令
    cmd = ['log', f'--max-count={max_count}', '--pretty=format:%H|%ad|%an|%s', '--date=short']

    if since:
        cmd.append(f'--since={since}')
    if until:
        cmd.append(f'--until={until}')
    if author:
        cmd.append(f'--author={author}')

    output = run_git_command(repo_path, cmd)

    if not output or "Error" in output:
        return {"commits": [], "total": 0, "error": output}

    commits = []
    for line in output.split('\n'):
        if not line.strip():
            continue

        parts = line.split('|', 3)
        if len(parts) < 4:
            continue

        commit_hash, date, author_name, message = parts[:4]

        # 获取变更文件和统计
        files_cmd = ['show', '--name-only', '--pretty=format:', commit_hash]
        files_output = run_git_command(repo_path, files_cmd)
        files = [f for f in files_output.split('\n') if f.strip() and not f.startswith('commit')]

        # 获取代码统计
        stats_cmd = ['show', '--stat', '--pretty=format:', commit_hash]
        stats_output = run_git_command(repo_path, stats_cmd)

        # 解析统计信息
        additions = 0
        deletions = 0
        for line in stats_output.split('\n'):
            match = re.search(r'(\d+) insertion', line)
            if match:
                additions += int(match.group(1))
            match = re.search(r'(\d+) deletion', line)
            if match:
                deletions += int(match.group(1))

        commits.append({
            "hash": commit_hash,
            "date": date,
            "author": author_name,
            "message": message,
            "files": files,
            "stats": {"additions": additions, "deletions": deletions}
        })

    return {"commits": commits, "total": len(commits)}


def analyze_file_changes(
    repo_path: str = ".",
    file_path: Optional[str] = None,
    commit_hash: Optional[str] = None,
    lines: int = 100
) -> Dict[str, Any]:
    """
    分析指定文件的代码变更详情

    Args:
        repo_path: git 仓库路径
        file_path: 文件路径
        commit_hash: 提交哈希，不指定则分析当前未提交的变更
        lines: 显示的 diff 行数

    Returns:
        包含变更详情的字典

    格式:
    {
        "file_path": "path/to/file",
        "stats": {"additions": 10, "deletions": 5},
        "diff_preview": "diff内容...",
        "language": "python"
    }
    """
    if commit_hash:
        # 分析特定提交的变更
        cmd = ['show', '--stat', f'--max-count={lines}', commit_hash]
        if file_path:
            cmd.append(file_path)
    else:
        # 分析当前未提交的变更
        cmd = ['diff', '--stat', 'HEAD']
        if file_path:
            cmd.append(file_path)

    output = run_git_command(repo_path, cmd)

    # 解析统计
    additions = 0
    deletions = 0
    for line in output.split('\n'):
        match = re.search(r'(\d+) insertion', line)
        if match:
            additions += int(match.group(1))
        match = re.search(r'(\d+) deletion', line)
        if match:
            deletions += int(match.group(1))

    # 获取 diff 预览
    diff_cmd = ['diff', 'HEAD']
    if file_path:
        diff_cmd.append(file_path)
    diff_cmd.append(f'| head -n {lines}')

    diff_output = run_git_command(repo_path, diff_cmd.split('|')[0].strip())

    # 推断语言类型
    language = "text"
    if file_path:
        ext = Path(file_path).suffix.lower()
        lang_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.rs': 'rust',
            '.go': 'go',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.md': 'markdown',
            '.toml': 'toml',
            '.css': 'css',
            '.html': 'html',
            '.sql': 'sql'
        }
        language = lang_map.get(ext, 'text')

    return {
        "file_path": file_path or "",
        "stats": {"additions": additions, "deletions": deletions},
        "diff_preview": diff_output[:5000] if diff_output else "",
        "language": language
    }


def generate_daily_report(
    repo_path: str = ".",
    days: int = 2,
    author: Optional[str] = None,
    include_file_details: bool = False
) -> str:
    """
    生成格式化的工作日报

    Args:
        repo_path: git 仓库路径
        days: 回溯天数
        author: 作者筛选
        include_file_details: 是否包含文件变更详情

    Returns:
        Markdown 格式的日报字符串
    """
    repo_path = get_repo_path(repo_path)

    # 计算日期范围
    today = datetime.now()
    dates = []

    for i in range(days):
        date = today - timedelta(days=i)
        dates.append({
            "label": "今天" if i == 0 else ("昨天" if i == 1 else f"{i}天前"),
            "date": date.strftime("%Y-%m-%d")
        })

    report_lines = ["# 工作日报", ""]
    overall_stats = {"commits": 0, "additions": 0, "deletions": 0}

    # 按日期分析
    for date_info in dates:
        date_str = date_info["date"]
        since = date_str
        until = (today - timedelta(days=date_info["label"] != "今天" and 1 or 0)).strftime("%Y-%m-%d")

        result = analyze_commits(repo_path, since=since, until=until, author=author)

        if not result["commits"]:
            report_lines.append(f"## {date_info['label']} ({date_str})")
            report_lines.append("")
            report_lines.append("*无提交记录*")
            report_lines.append("")
            continue

        report_lines.append(f"## {date_info['label']} ({date_str})")
        report_lines.append("")

        # 统计
        day_additions = sum(c["stats"]["additions"] for c in result["commits"])
        day_deletions = sum(c["stats"]["deletions"] for c in result["commits"])
        overall_stats["commits"] += result["total"]
        overall_stats["additions"] += day_additions
        overall_stats["deletions"] += day_deletions

        # 按提交展示
        for commit in result["commits"]:
            report_lines.append(f"### {commit['message']}")
            report_lines.append("")
            report_lines.append(f"- **作者**: {commit['author']}")
            report_lines.append(f"- **提交**: `{commit['hash'][:8]}`")
            report_lines.append(f"- **变更**: +{commit['stats']['additions']} / -{commit['stats']['deletions']}")
            report_lines.append(f"- **文件数**: {len(commit['files'])}")

            if include_file_details and commit['files']:
                report_lines.append(f"- **变更文件**:")
                for f in commit['files'][:10]:  # 限制显示数量
                    report_lines.append(f"  - `{f}`")
                if len(commit['files']) > 10:
                    report_lines.append(f"  - ... 还有 {len(commit['files']) - 10} 个文件")

            report_lines.append("")

    # 总体统计
    report_lines.append("## 总体统计")
    report_lines.append("")
    report_lines.append("| 指标 | 数值 |")
    report_lines.append("|------|------|")
    report_lines.append(f"| 总提交数 | {overall_stats['commits']} |")
    report_lines.append(f"| 新增代码 | {overall_stats['additions']} 行 |")
    report_lines.append(f"| 删除代码 | {overall_stats['deletions']} 行 |")
    net_change = overall_stats['additions'] - overall_stats['deletions']
    report_lines.append(f"| 净变化 | {net_change:+} 行 |")

    return "\n".join(report_lines)


def get_git_stats(repo_path: str = ".") -> Dict[str, Any]:
    """
    获取 git 仓库统计信息

    Args:
        repo_path: git 仓库路径

    Returns:
        仓库统计信息字典
    """
    repo_path = get_repo_path(repo_path)

    # 总提交数
    total_commits = run_git_command(repo_path, ['rev-list', '--count', 'HEAD']).strip()

    # 分支数
    branches = run_git_command(repo_path, ['branch', '-a']).strip().split('\n')
    branch_count = len([b for b in branches if b.strip() and not b.startswith('*')])

    # 作者统计
    authors_cmd = ['shortlog', '-sn', '--all', '--no-merges']
    authors_output = run_git_command(repo_path, authors_cmd)
    authors = []
    for line in authors_output.split('\n')[:10]:
        parts = line.strip().split('\t')
        if len(parts) == 2:
            authors.append({"commits": parts[0], "name": parts[1]})

    # 最近修改的文件
    recent_files_cmd = ['diff', '--name-only', 'HEAD~10', 'HEAD']
    recent_files = [f for f in run_git_command(repo_path, recent_files_cmd).split('\n') if f.strip()]

    return {
        "total_commits": int(total_commits) if total_commits.isdigit() else 0,
        "branch_count": branch_count,
        "top_authors": authors,
        "recent_files": list(set(recent_files))[:20]
    }
