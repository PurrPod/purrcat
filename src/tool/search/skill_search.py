"""Skill 搜索模块 - 搜索和加载系统技能"""

import os
from pathlib import Path
from typing import List, Dict, Any

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


DEFAULT_SKILL_PATH = Path("data/skill")


def _parse_skill_md(file_path: Path) -> Dict[str, Any]:
    """解析 SKILL.md 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    metadata = {}
    content = text
    
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1]
            content = parts[2].strip()
            for line in frontmatter_str.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip()
    
    return {"metadata": metadata, "content": content}


class SkillSearcher:
    """技能搜索器"""
    
    def __init__(self, skill_dir: Path = DEFAULT_SKILL_PATH):
        self.skills = []
        self.corpus = []
        self._load_skills(skill_dir)
        self.vectorizer = TfidfVectorizer()
        if self.corpus:
            self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

    def _load_skills(self, skill_dir: Path):
        """遍历 Skill 目录，解析 SKILL.md"""
        if not skill_dir.exists() or not skill_dir.is_dir():
            return
        
        for item in skill_dir.iterdir():
            if item.is_dir():
                md_file = item / "SKILL.md"
                if md_file.exists():
                    parsed_data = _parse_skill_md(md_file)
                    metadata = parsed_data["metadata"]
                    name = metadata.get("name", item.name)
                    desc = metadata.get("description", metadata.get("desc", ""))
                    content = parsed_data.get("content", "")
                    
                    self.skills.append({
                        "name": name,
                        "description": desc,
                        "dir_name": item.name
                    })
                    text_representation = f"{name} {desc} {content}"
                    self.corpus.append(text_representation)

    def _process_query(self, query: str) -> str:
        """处理查询词：分词并过滤"""
        words = jieba.lcut(query)
        processed_tokens = []
        for word in words:
            word = word.strip()
            if len(word) == 0 or word in "，。！？、,!?()（）":
                continue
            processed_tokens.append(word.lower())
        return " ".join(processed_tokens)

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """执行搜索并返回匹配度最高的前 K 个技能"""
        if not self.corpus:
            return []
        
        expanded_query = self._process_query(query)
        query_vector = self.vectorizer.transform([expanded_query])
        similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
        top_k_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_k_indices:
            if similarities[idx] > 0:
                results.append({
                    "score": round(float(similarities[idx]), 4),
                    "skill": self.skills[idx]
                })
        
        return results


def search_skills(query: str, top_k: int = 3) -> tuple:
    """
    搜索技能
    
    Args:
        query: 搜索查询词
        top_k: 返回前 K 个结果
    
    Returns:
        (results, error_message)
    """
    try:
        skill_searcher = SkillSearcher(DEFAULT_SKILL_PATH)
        results = skill_searcher.search(query, top_k)
        return results, None
    except Exception as e:
        return [], f"Skill 搜索异常: {e}"


def load_skill(name: str) -> dict:
    """
    加载技能文件详情
    
    Args:
        name: 技能名称
    
    Returns:
        技能详情字典
    """
    base_dir = Path(DEFAULT_SKILL_PATH)
    target_dir = base_dir / name
    md_file = target_dir / "SKILL.md"
    
    if not md_file.exists():
        # 尝试按目录名查找
        for item in base_dir.iterdir():
            if item.is_dir():
                dir_md = item / "SKILL.md"
                if dir_md.exists():
                    parsed = _parse_skill_md(dir_md)
                    if parsed["metadata"].get("name") == name:
                        md_file = dir_md
                        target_dir = item
                        break
    
    if not md_file.exists():
        raise FileNotFoundError(f"找不到技能: {name}")
    
    parsed_data = _parse_skill_md(md_file)
    metadata = parsed_data["metadata"]
    content = parsed_data["content"]
    
    return {
        "name": metadata.get("name", name),
        "description": metadata.get("description", metadata.get("desc", "")),
        "content": content,
        "directory": str(target_dir)
    }