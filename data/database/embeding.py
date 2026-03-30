import os
import json
import re
import argparse
import numpy as np
import faiss
from tqdm import tqdm
from typing import List
from sentence_transformers import SentenceTransformer


def chunk_text(text: str, chunk_size: int = 300, chunk_overlap: int = 50) -> List[str]:
    """
    按优先级：双换行(段落) -> 单换行 -> 句末标点 -> 逗号分号 -> 空格 -> 强行截断
    """
    if not text.strip():
        return []

    separators = [
        "\n\n",  # Markdown 段落
        "\n",  # 换行
        r"([。！？])",  # 强中文句末标点
        r"([；，])",  # 弱中文句内标点
        " ",  # 空格
        ""  # 强切
    ]

    def _split_recursively(text_to_split: str, sep_index: int) -> List[str]:
        if len(text_to_split) <= chunk_size or sep_index >= len(separators):
            return [text_to_split]

        separator = separators[sep_index]
        splits = []

        if separator == "":
            splits = [text_to_split[i:i + chunk_size] for i in range(0, len(text_to_split), chunk_size)]
        elif separator.startswith("("):
            raw_splits = re.split(separator, text_to_split)
            for i in range(0, len(raw_splits) - 1, 2):
                if raw_splits[i] or raw_splits[i + 1]:
                    splits.append(raw_splits[i] + raw_splits[i + 1])
            if len(raw_splits) % 2 != 0 and raw_splits[-1]:
                splits.append(raw_splits[-1])
        else:
            raw_splits = text_to_split.split(separator)
            splits = [s + separator if i < len(raw_splits) - 1 else s for i, s in enumerate(raw_splits) if s]

        final_splits = []
        for s in splits:
            if len(s) > chunk_size:
                final_splits.extend(_split_recursively(s, sep_index + 1))
            else:
                if s.strip():
                    final_splits.append(s)

        return final_splits

    # 把全文打碎成不超过 chunk_size 的语义碎片
    semantic_splits = _split_recursively(text, 0)

    # 将碎片拼装成最终的 chunks，并保证 Overlap
    chunks = []
    current_chunk_pieces = []
    current_length = 0

    for piece in semantic_splits:
        piece_len = len(piece)

        # 当加入新句子会超长，封箱当前 Chunk
        if current_length + piece_len > chunk_size and current_chunk_pieces:
            # 1. 保存当前 Chunk
            chunk_text_str = "".join(current_chunk_pieces).strip()
            if chunk_text_str:
                chunks.append(chunk_text_str)

            # 计算真正的 Overlap (重叠部分)
            # 逻辑：从当前 Chunk 的最后一句开始往前倒推，直到总长度 "大于等于" 我们要求的重叠长度
            overlap_length = 0
            keep_for_next = []
            for past_piece in reversed(current_chunk_pieces):
                keep_for_next.insert(0, past_piece)
                overlap_length += len(past_piece)

                # 只要保留的句子字数达到了设定的重叠阈值，就停止倒推
                if overlap_length >= chunk_overlap:
                    break

            # 安全兜底：如果单句话特别长，导致把整个 Chunk 都留给了下一个，会引发死循环
            # 强制踢掉第一句话
            if len(keep_for_next) == len(current_chunk_pieces):
                popped = keep_for_next.pop(0)
                overlap_length -= len(popped)

            # 把留下来的重叠句子，作为下一个 Chunk 的开头
            current_chunk_pieces = keep_for_next
            current_length = overlap_length

        # 放入新句子
        current_chunk_pieces.append(piece)
        current_length += piece_len

    # 打包最后剩下的文本
    if current_chunk_pieces:
        chunk_text_str = "".join(current_chunk_pieces).strip()
        if chunk_text_str:
            chunks.append(chunk_text_str)

    return chunks


def main():
    parser = argparse.ArgumentParser(description="RAG构建工具")
    parser.add_argument("--db_name", type=str, required=True, help="数据库名称")
    parser.add_argument("--model", type=str, default=None, help="嵌入模型")
    parser.add_argument("--base_dir", type=str, default="data/database", help="数据库根目录")
    parser.add_argument("--batch_size", type=int, default=500, help="每批次落盘的数据量")
    args = parser.parse_args()
    if not args.model:
        # 使用默认 embedding 模型
        args.model = "BAAI/bge-small-zh-v1.5"
    db_dir = os.path.join(args.base_dir, args.db_name)
    md_path = os.path.join(db_dir, f"{args.db_name}.md")
    json_path = os.path.join(db_dir, f"{args.db_name}.json")
    index_path = os.path.join(db_dir, f"{args.db_name}.index")
    print(f"=== 🚀 开始构建/续传知识库: {args.db_name} ===")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print(f"⚠️ 目录 {db_dir} 不存在，已为您创建。请放入 {args.db_name}.md 后重试。")
        return
    if not os.path.exists(json_path):
        if not os.path.exists(md_path):
            print(f"❌ 错误: 找不到 {md_path}。")
            return
        print(f"📖 首次运行，正在读取并切分源文件: {md_path} ...")
        with open(md_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
        chunks = chunk_text(raw_text)
        documents = [{"text": chunk, "meta": {"source": f"{args.db_name}.md", "chunk_id": i}} for i, chunk in
                     enumerate(chunks)]
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(documents, f, ensure_ascii=False, indent=4)
        print(f"✂️ 切分完成，共生成 {len(documents)} 个文本块，已持久化到 JSON。")
    else:
        print(f"📂 读取已有的 JSON 文本数据: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            documents = json.load(f)
    total_docs = len(documents)
    if total_docs == 0:
        print("⚠️ 数据为空，退出。")
        return
    print(f"🧠 正在加载模型: {args.model} ...")
    model = SentenceTransformer(args.model)
    dimension = model.get_sentence_embedding_dimension()
    processed_count = 0
    if os.path.exists(index_path):
        try:
            index = faiss.read_index(index_path)
            processed_count = index.ntotal
            print(f"🛡️ 触发防中断机制！检测到已有 {processed_count} 条向量数据。")
        except Exception as e:
            print(f"⚠️ 索引文件损坏: {e}，将重新构建...")
            index = faiss.index_factory(dimension, "HNSW32,Flat", faiss.METRIC_INNER_PRODUCT)
    else:
        print("✨ 从头开始构建...")
        index = faiss.index_factory(dimension, "HNSW32,Flat", faiss.METRIC_INNER_PRODUCT)
    if processed_count >= total_docs:
        print("🎉 检测到该知识库已全部构建完毕！")
        return
    remaining_docs = documents[processed_count:]
    print(f"🧠 开始处理剩余的 {len(remaining_docs)} 条数据...")
    with tqdm(total=total_docs, initial=processed_count, desc="<|向量化进度|>", unit="条") as pbar:
        for i in range(0, len(remaining_docs), args.batch_size):
            batch = remaining_docs[i: i + args.batch_size]
            texts_to_encode = [d['text'] for d in batch]
            embeddings = model.encode(texts_to_encode, normalize_embeddings=True, show_progress_bar=False)
            index.add(np.array(embeddings).astype('float32'))
            faiss.write_index(index, index_path)
            pbar.update(len(batch))
    print(f"\n🎉 任务完成，向量库已保存至: {index_path}")


if __name__ == "__main__":
    main()