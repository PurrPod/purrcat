import os
import base64
from github import Github, GithubException
from typing import List, Dict, Optional, Union

# --- 单例实例管理 ---
_tool_instance = None

def get_tool():
    global _tool_instance
    if _tool_instance is None:
        token = "YOUR_GITHUB_TOKEN"
        if not token:
            raise ValueError("❌ 未找到环境变量 GITHUB_TOKEN，请先配置 GitHub Token。")
        _tool_instance = GitHubMCPTools(token)
    return _tool_instance

class GitHubMCPTools:
    """GitHub Model Context Protocol 工具集 (核心逻辑)"""
    def __init__(self, token: str):
        self.g = Github(token)
        self.user = self.g.get_user()

    def _get_repo(self, repo_name: str):
        try:
            return self.g.get_repo(repo_name)
        except GithubException as e:
            raise Exception(f"无法找到仓库 {repo_name}: {e.data.get('message')}")

    def read_file(self, repo_name: str, file_path: str, branch: str = "main") -> str:
        try:
            repo = self._get_repo(repo_name)
            contents = repo.get_contents(file_path, ref=branch)
            return contents.decoded_content.decode('utf-8')
        except Exception as e:
            return f"❌ 读取失败: {str(e)}"

    def create_or_update_file(self, repo_name: str, file_path: str, content: str, commit_message: str, branch: str = "main") -> str:
        try:
            repo = self._get_repo(repo_name)
            try:
                contents = repo.get_contents(file_path, ref=branch)
                repo.update_file(file_path, commit_message, content, contents.sha, branch=branch)
                return f"✅ 文件已更新: {file_path}"
            except GithubException:
                repo.create_file(file_path, commit_message, content, branch=branch)
                return f"✅ 文件已创建: {file_path}"
        except Exception as e:
            return f"❌ 操作失败: {str(e)}"

    def search_code(self, query: str, repo_name: Optional[str] = None) -> List[str]:
        try:
            final_query = f"{query} repo:{repo_name}" if repo_name else query
            result = self.g.search_code(final_query)
            return [f"[{f.repository.full_name}] {f.path}: {f.html_url}" for f in result[:10]]
        except Exception as e:
            return [f"❌ 搜索失败: {str(e)}"]

    def get_tree(self, repo_name: str, branch: str = "main", recursive: bool = True) -> List[str]:
        try:
            repo = self._get_repo(repo_name)
            sha = repo.get_branch(branch).commit.sha
            tree = repo.get_git_tree(sha, recursive=recursive).tree
            return [element.path for element in tree if element.type == 'blob'][:50]
        except Exception as e:
            return [f"❌ 获取树失败: {str(e)}"]

    def create_issue(self, repo_name: str, title: str, body: str, labels: List[str] = None) -> str:
        try:
            repo = self._get_repo(repo_name)
            issue = repo.create_issue(title=title, body=body, labels=labels or [])
            return f"✅ Issue 创建成功: #{issue.number} ({issue.html_url})"
        except Exception as e:
            return f"❌ 创建 Issue 失败: {str(e)}"

    def list_issues(self, repo_name: str, state: str = "open") -> str:
        try:
            repo = self._get_repo(repo_name)
            issues = repo.get_issues(state=state)
            result = [f"#{i.number} {i.title} ({i.updated_at})" for i in issues[:20]]
            return "\n".join(result) if result else "无 Issue"
        except Exception as e:
            return f"❌ 获取 Issues 失败: {str(e)}"

    def get_issue(self, repo_name: str, issue_number: int) -> str:
        try:
            repo = self._get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            return f"标题: {issue.title}\n状态: {issue.state}\n内容: {issue.body}"
        except Exception as e:
            return f"❌ 获取详情失败: {str(e)}"

    def update_issue(self, repo_name: str, issue_number: int, state: str = None, body: str = None) -> str:
        try:
            repo = self._get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            if state: issue.edit(state=state)
            if body: issue.edit(body=body)
            return f"✅ Issue #{issue_number} 更新成功"
        except Exception as e:
            return f"❌ 更新失败: {str(e)}"

    def add_issue_comment(self, repo_name: str, issue_number: int, body: str) -> str:
        try:
            repo = self._get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            comment = issue.create_comment(body)
            return f"✅ 评论成功: {comment.html_url}"
        except Exception as e:
            return f"❌ 评论失败: {str(e)}"

    def create_pull_request(self, repo_name: str, title: str, body: str, head: str, base: str = "main") -> str:
        try:
            repo = self._get_repo(repo_name)
            pr = repo.create_pull(title=title, body=body, head=head, base=base)
            return f"✅ PR 创建成功: #{pr.number} ({pr.html_url})"
        except Exception as e:
            return f"❌ 创建 PR 失败: {str(e)}"

    def list_pull_requests(self, repo_name: str, state: str = "open") -> str:
        try:
            repo = self._get_repo(repo_name)
            prs = repo.get_pulls(state=state)
            result = [f"#{p.number} {p.title} (Head: {p.head.ref})" for p in prs[:20]]
            return "\n".join(result) if result else "无 PR"
        except Exception as e:
            return f"❌ 获取 PR 列表失败: {str(e)}"

    def get_pull_request(self, repo_name: str, pr_number: int) -> str:
        try:
            repo = self._get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            return f"标题: {pr.title}\n状态: {pr.state}\n合并状态: {pr.merged}\nDiff URL: {pr.diff_url}"
        except Exception as e:
            return f"❌ 获取 PR 详情失败: {str(e)}"

    def merge_pull_request(self, repo_name: str, pr_number: int, merge_method: str = "merge") -> str:
        try:
            repo = self._get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            status = pr.merge(merge_method=merge_method)
            return f"✅ 合并结果: {status.message} (SHA: {status.sha})"
        except Exception as e:
            return f"❌ 合并失败: {str(e)}"

    def add_pr_comment(self, repo_name: str, pr_number: int, body: str) -> str:
        return self.add_issue_comment(repo_name, pr_number, body)

    def create_branch(self, repo_name: str, new_branch: str, source_branch: str = "main") -> str:
        try:
            repo = self._get_repo(repo_name)
            source = repo.get_branch(source_branch)
            repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=source.commit.sha)
            return f"✅ 分支 '{new_branch}' 创建成功 (基于 {source_branch})"
        except Exception as e:
            return f"❌ 创建分支失败: {str(e)}"

    def list_branches(self, repo_name: str) -> List[str]:
        try:
            repo = self._get_repo(repo_name)
            return [b.name for b in repo.get_branches()]
        except Exception as e:
            return [f"❌ 获取分支失败: {str(e)}"]

    def list_commits(self, repo_name: str, branch: str = "main", limit: int = 10) -> str:
        try:
            repo = self._get_repo(repo_name)
            commits = repo.get_commits(sha=branch)[:limit]
            return "\n".join([f"{c.sha[:7]} - {c.commit.message} ({c.commit.author.name})" for c in commits])
        except Exception as e:
            return f"❌ 获取提交历史失败: {str(e)}"

    def get_commit(self, repo_name: str, sha: str) -> str:
        try:
            repo = self._get_repo(repo_name)
            commit = repo.get_commit(sha)
            files_changed = [f.filename for f in commit.files]
            return f"Message: {commit.commit.message}\nAuthor: {commit.commit.author.name}\nFiles: {files_changed}"
        except Exception as e:
            return f"❌ 获取提交详情失败: {str(e)}"

    def search_repositories(self, query: str) -> List[str]:
        try:
            repos = self.g.search_repositories(query, sort="stars", order="desc")
            return [f"{r.full_name} (⭐ {r.stargazers_count})" for r in repos[:10]]
        except Exception as e:
            return [f"❌ 搜索仓库失败: {str(e)}"]

    def fork_repository(self, repo_name: str) -> str:
        try:
            repo = self._get_repo(repo_name)
            my_fork = self.user.create_fork(repo)
            return f"✅ Fork 成功: {my_fork.html_url}"
        except Exception as e:
            return f"❌ Fork 失败: {str(e)}"

    def get_current_user(self) -> str:
        """21. 获取当前登录用户信息"""
        try:
            return f"Login: {self.user.login}\nName: {self.user.name}\nEmail: {self.user.email}"
        except Exception as e:
            return f"❌ 获取用户信息失败: {str(e)}"

    def list_user_repos(self, affiliation: str = "owner,collaborator", limit: int = 30) -> str:
        """22. 列出当前用户有权限的仓库"""
        try:
            # affiliation 参数控制: owner(自己拥有的), collaborator(被邀请协作的), organization_member(组织内的)
            repos = self.user.get_repos(affiliation=affiliation, sort="updated", direction="desc")
            result = []
            for r in repos[:limit]:
                result.append(f"{r.full_name} [{r.visibility}] (⭐{r.stargazers_count})")
            return "\n".join(result) if result else "无仓库"
        except Exception as e:
            return f"❌ 获取仓库列表失败: {str(e)}"

# --- 导出函数 (MMCP 调用入口) ---

def read_file(repo_name: str, file_path: str, branch: str = "main"):
    return get_tool().read_file(repo_name, file_path, branch)

def create_or_update_file(repo_name: str, file_path: str, content: str, commit_message: str, branch: str = "main"):
    return get_tool().create_or_update_file(repo_name, file_path, content, commit_message, branch)

def search_code(query: str, repo_name: str = None):
    return get_tool().search_code(query, repo_name)

def get_tree(repo_name: str, branch: str = "main", recursive: bool = True):
    return get_tool().get_tree(repo_name, branch, recursive)

def create_issue(repo_name: str, title: str, body: str, labels: list = None):
    return get_tool().create_issue(repo_name, "[MA]"+title, body, labels)

def list_issues(repo_name: str, state: str = "open"):
    return get_tool().list_issues(repo_name, state)

def get_issue(repo_name: str, issue_number: int):
    return get_tool().get_issue(repo_name, issue_number)

def update_issue(repo_name: str, issue_number: int, state: str = None, body: str = None):
    return get_tool().update_issue(repo_name, issue_number, state, body)

def add_issue_comment(repo_name: str, issue_number: int, body: str):
    return get_tool().add_issue_comment(repo_name, issue_number, "[MA]"+body)

def create_pull_request(repo_name: str, title: str, body: str, head: str, base: str = "main"):
    return get_tool().create_pull_request(repo_name, "[MA]"+title, body, head, base)

def list_pull_requests(repo_name: str, state: str = "open"):
    return get_tool().list_pull_requests(repo_name, state)

def get_pull_request(repo_name: str, pr_number: int):
    return get_tool().get_pull_request(repo_name, pr_number)

def merge_pull_request(repo_name: str, pr_number: int, merge_method: str = "merge"):
    return get_tool().merge_pull_request(repo_name, pr_number, merge_method)

def add_pr_comment(repo_name: str, pr_number: int, body: str):
    return get_tool().add_pr_comment(repo_name, pr_number, body)

def create_branch(repo_name: str, new_branch: str, source_branch: str = "main"):
    return get_tool().create_branch(repo_name, new_branch, source_branch)

def list_branches(repo_name: str):
    return get_tool().list_branches(repo_name)

def list_commits(repo_name: str, branch: str = "main", limit: int = 10):
    return get_tool().list_commits(repo_name, branch, limit)

def get_commit(repo_name: str, sha: str):
    return get_tool().get_commit(repo_name, sha)

def search_repositories(query: str):
    return get_tool().search_repositories(query)

def fork_repository(repo_name: str):
    return get_tool().fork_repository(repo_name)

def get_current_user():
    return get_tool().get_current_user()

def list_user_repos(affiliation: str = "owner,collaborator", limit: int = 30):
    return get_tool().list_user_repos(affiliation, limit)