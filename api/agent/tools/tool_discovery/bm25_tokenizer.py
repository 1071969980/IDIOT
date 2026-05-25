import re
from typing import List

import bm25s
import jieba.posseg as pseg
import Stemmer


class BM25MultilingualTokenizer:
    """
    中英文混合分词器，专为 BM25s 检索优化
    - 保护邮箱/URL/数字单位不被切散
    - 英文缩写规范化（don't -> do not）
    - 中文使用 jieba 并过滤无意义虚词
    """
    
    def __init__(self, enable_protection=True, stemmer=None, stopwords="en"):
        self.enable_protection = enable_protection
        # 使用 bm25s 内置英文分词器所需组件
        self.stemmer = stemmer if stemmer is not None else Stemmer.Stemmer("english")
        self.stopwords = stopwords  # 可以是 "en" 或自定义停用词列表
        
        # 1. 特殊实体保护规则（占位符 + 原串映射）
        self.protected_patterns = [
            (re.compile(r'\b[\w.-]+@[\w.-]+\.\w+\b'), 'EMAIL'),
            (re.compile(r'https?://[^\s]+'), 'URL'),
            (re.compile(r'\d+\.\d+\.\d+'), 'VERSION'),
            (re.compile(r'\d+[a-zA-Z]+'), 'UNIT_ENG'),      # 20GB
            (re.compile(r'\d+[公里|米|千克|小时|分钟|秒]'), 'UNIT_CH')  # 5公里
        ]
        self.protected_map = {}
        
        # 2. 英文缩写展开表（可根据需要扩展）
        self.contraction_map = {
            "don't": "do not",
            "doesn't": "does not",
            "didn't": "did not",
            "can't": "cannot",
            "couldn't": "could not",
            "won't": "will not",
            "wouldn't": "would not",
            "shouldn't": "should not",
            "i'm": "i am",
            "you're": "you are",
            "we're": "we are",
            "they're": "they are",
            "it's": "it is",
            "he's": "he is",
            "she's": "she is",
            "that's": "that is",
            "what's": "what is",
            "let's": "let us",
        }
    
    def _pre_protect(self, text: str) -> str:
        """将特殊实体替换为占位符"""
        if not self.enable_protection:
            return text
        self.protected_map.clear()
        for i, (pattern, typ) in enumerate(self.protected_patterns):
            for match in pattern.finditer(text):
                placeholder = f"__PROTECT_{typ}_{i}__"
                self.protected_map[placeholder] = match.group()
                text = text.replace(match.group(), placeholder)
        return text
    
    def _restore(self, tokens: List[str]) -> List[str]:
        """将占位符还原为原始实体（小写）"""
        if not self.enable_protection:
            return tokens
        restored = []
        for token in tokens:
            if token in self.protected_map:
                restored.append(self.protected_map[token].lower())
            else:
                restored.append(token)
        return restored
    
    def _tokenize_english(self, text: str) -> List[str]:
        """
        BM25s 风格英文分词 + 缩写处理
        仿照 bm25s 官方示例：re.findall(r"\w+", text.lower()) 但支持连字符和缩写
        """
        # 将常见缩写展开为完整形式（例如 don't -> do not）
        text_lower = text.lower()
        for contraction, full in self.contraction_map.items():
            # 使用单词边界确保精确替换
            text_lower = re.sub(r'\b' + re.escape(contraction) + r'\b', full, text_lower)
        
        # 调用 bm25s 官方分词，返回 Tokenized 对象（ids + vocab）
        tok = bm25s.tokenize(
            [text_lower],           # 输入必须是字符串列表
            stopwords=self.stopwords,
            stemmer=self.stemmer,
            show_progress=False
        )
        if not isinstance(tok, bm25s.tokenization.Tokenized):
            raise TypeError(f"bm25s.tokenize 应返回 Tokenized 对象，实际为 {type(tok)}")
        # 将 id 反查回字符串
        inv_vocab = {v: k for k, v in tok.vocab.items()}
        return [inv_vocab[i] for i in tok.ids[0]]
    
    def tokenize(self, text: str) -> List[str]:
        # 保护特殊实体
        text = self._pre_protect(text)
        
        tokens = []
        # 中英文分块
        pattern = re.compile(r'([\u4e00-\u9fff]+)|([a-zA-Z0-9\-\.]+)')
        for chinese_chunk, eng_chunk in pattern.findall(text):
            if chinese_chunk:
                # 中文部分：jieba 词性标注过滤虚词
                words = pseg.cut(chinese_chunk)
                for word, flag in words:
                    # 过滤掉助词、介词、连词、标点等
                    if flag not in ['x', 'u', 'p', 'c', 'e', 'y', 'o']:
                        tokens.append(word)
            if eng_chunk:
                # 英文部分：调用 BM25s 风格分词
                tokens.extend(self._tokenize_english(eng_chunk))
        
        # 还原受保护的特殊实体
        tokens = self._restore(tokens)
        return tokens