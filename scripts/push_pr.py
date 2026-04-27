"""
快速推送 Trading Expert 改动到 GitHub PR
用法: python scripts/push_pr.py YOUR_GITHUB_TOKEN
"""
import sys, requests, base64, os, json

def push(token):
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    owner, repo = 'PurrPod', 'purrcat'
    
    # 获取 main
    r = requests.get(f'https://api.github.com/repos/{owner}/{repo}/git/refs/heads/main', headers=headers)
    main_sha = r.json()['object']['sha']
    
    # 创建分支
    branch = 'feat/trading-expert-pro'
    r = requests.post(f'https://api.github.com/repos/{owner}/{repo}/git/refs',
                      headers=headers, json={'ref': f'refs/heads/{branch}', 'sha': main_sha})
    if r.status_code == 422:  # 已存在
        r = requests.get(f'https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}', headers=headers)
    head_sha = r.json()['object']['sha']
    
    r = requests.get(f'https://api.github.com/repos/{owner}/{repo}/git/commits/{head_sha}', headers=headers)
    base_tree = r.json()['tree']['sha']
    
    # 文件列表
    base = '/agent_vm/cat-in-cup'
    files = {
        'src/harness/expert/trading/extend_tool/kv_cache.py': f'{base}/src/harness/expert/trading/extend_tool/kv_cache.py',
        'src/harness/expert/trading/extend_tool/data_sources.py': f'{base}/src/harness/expert/trading/extend_tool/data_sources.py',
        'src/harness/expert/trading/extend_tool/__init__.py': f'{base}/src/harness/expert/trading/extend_tool/__init__.py',
        'src/harness/expert/trading/task.py': f'{base}/src/harness/expert/trading/task.py',
    }
    
    blobs = {}
    for path, local in files.items():
        with open(local, 'rb') as f:
            content = base64.b64encode(f.read()).decode()
        r = requests.post(f'https://api.github.com/repos/{owner}/{repo}/git/blobs',
                          headers=headers, json={'content': content, 'encoding': 'base64'})
        blobs[path] = r.json()['sha']
        print(f'  {path}: {blobs[path][:8]}')
    
    tree = [{'path': p, 'mode': '100644', 'type': 'blob', 'sha': s} for p, s in blobs.items()]
    r = requests.post(f'https://api.github.com/repos/{owner}/{repo}/git/trees',
                      headers=headers, json={'base_tree': base_tree, 'tree': tree})
    new_tree = r.json()['sha']
    
    r = requests.post(f'https://api.github.com/repos/{owner}/{repo}/git/commits',
                      headers=headers, json={
                          'message': 'feat: professional trading expert',
                          'tree': new_tree, 'parents': [head_sha]
                      })
    new_commit = r.json()['sha']
    
    r = requests.patch(f'https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}',
                       headers=headers, json={'sha': new_commit, 'force': True})
    print(f'Push: {"OK" if r.status_code==200 else "FAIL"}')
    
    # Create PR
    r = requests.post(f'https://api.github.com/repos/{owner}/{repo}/pulls',
                      headers=headers, json={
                          'title': 'feat: professional trading expert - 3-phase pipeline + KV cache + financial tools',
                          'head': branch, 'base': 'main',
                          'body': open(f'{base}/scripts/push_pr.py').read()[:200] + '\n\n详见 commit message'
                      })
    print(f'PR: {r.json().get("html_url", r.json().get("message","?"))}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts/push_pr.py YOUR_GITHUB_TOKEN')
        sys.exit(1)
    push(sys.argv[1])
