"""OCR文字处理模块"""
import re
from typing import Dict, Optional
import jieba
from loguru import logger


class OCRProcessor:
    """OCR文字处理器"""
    
    def __init__(self):
        """初始化OCR处理器"""
        # 初始化jieba分词
        jieba.initialize()
        logger.info("OCR处理器初始化完成")
    
    def clean_text(self, text: str) -> str:
        """
        清理文字
        
        Args:
            text: 原始文字
        
        Returns:
            清理后的文字
        """
        if not text:
            return ""
        
        # 去除特殊字符，保留中文、英文、数字、常见标点
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s，。！？：；、]', '', text)
        
        # 规范化空格
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def extract_title(self, text: str) -> str:
        """
        提取书名
        
        Args:
            text: OCR文字
        
        Returns:
            书名
        """
        if not text:
            return ""
        
        # 方法1：查找"书名："、"标题："等关键词
        patterns = [
            r'书名[：:]\s*([^\n]+)',
            r'标题[：:]\s*([^\n]+)',
            r'书名\s+([^\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                if len(title) > 0 and len(title) < 100:  # 书名通常不会太长
                    return title
        
        # 方法2：提取第一行（通常是书名）
        lines = text.split('\n')
        for line in lines[:3]:  # 检查前3行
            line = line.strip()
            if line and len(line) < 100:
                # 排除明显的非书名行
                if not re.match(r'^(作者|出版社|ISBN|价格)', line):
                    return line
        
        # 方法3：如果都没找到，返回前50个字符
        return text[:50].strip()
    
    def extract_author(self, text: str) -> str:
        """
        提取作者
        
        Args:
            text: OCR文字
        
        Returns:
            作者
        """
        if not text:
            return ""
        
        # 查找"作者："、"著："等关键词
        patterns = [
            r'作者[：:]\s*([^\n]+)',
            r'著[：:]\s*([^\n]+)',
            r'编[：:]\s*([^\n]+)',
            r'作者\s+([^\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                author = match.group(1).strip()
                # 去除可能的出版社等信息
                author = re.sub(r'[，,].*', '', author)
                if len(author) > 0 and len(author) < 50:
                    return author
        
        return ""
    
    def extract_isbn(self, text: str) -> str:
        """
        提取ISBN
        
        Args:
            text: OCR文字
        
        Returns:
            ISBN
        """
        if not text:
            return ""
        
        # 匹配ISBN格式
        patterns = [
            r'ISBN[：:\s]*([0-9\-X]+)',
            r'978[0-9\-]+',  # ISBN-13格式
            r'[0-9]{13}',  # 13位数字
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                isbn = match.group(0) if match.lastindex is None else match.group(1)
                isbn = re.sub(r'[^\dX]', '', isbn)  # 只保留数字和X
                if len(isbn) >= 10:  # ISBN至少10位
                    return isbn
        
        return ""
    
    def extract_keywords(self, text: str, max_keywords: int = 10) -> str:
        """
        提取关键词
        
        Args:
            text: OCR文字
            max_keywords: 最大关键词数量
        
        Returns:
            关键词（逗号分隔）
        """
        if not text:
            return ""
        
        # 使用jieba分词
        words = jieba.cut(text)
        
        # 过滤停用词和短词
        stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        
        keywords = []
        for word in words:
            word = word.strip()
            if len(word) >= 2 and word not in stop_words:
                keywords.append(word)
        
        # 去重并限制数量
        keywords = list(dict.fromkeys(keywords))[:max_keywords]
        
        return ','.join(keywords)
    
    def generate_summary(self, text: str, max_length: int = 500) -> str:
        """
        生成摘要（前N个字符）
        
        Args:
            text: OCR文字
            max_length: 最大长度
        
        Returns:
            摘要
        """
        if not text:
            return ""
        
        # 清理文字
        text = self.clean_text(text)
        
        # 截取前N个字符
        if len(text) <= max_length:
            return text
        
        # 尝试在句子边界截断
        truncated = text[:max_length]
        last_period = max(
            truncated.rfind('。'),
            truncated.rfind('！'),
            truncated.rfind('？'),
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?')
        )
        
        if last_period > max_length * 0.7:  # 如果找到的标点在70%位置之后
            return truncated[:last_period + 1]
        
        return truncated
    
    def process_ocr_text(self, ocr_text: str) -> Dict[str, str]:
        """
        处理OCR文字，提取结构化信息
        
        Args:
            ocr_text: OCR原始文字
        
        Returns:
            结构化信息字典
        """
        if not ocr_text:
            return {
                "ocr_title": "",
                "ocr_author": "",
                "ocr_summary": "",
                "ocr_keywords": ""
            }
        
        # 清理文字
        cleaned_text = self.clean_text(ocr_text)
        
        # 提取各项信息
        result = {
            "ocr_title": self.extract_title(cleaned_text),
            "ocr_author": self.extract_author(cleaned_text),
            "ocr_summary": self.generate_summary(cleaned_text),
            "ocr_keywords": self.extract_keywords(cleaned_text)
        }
        
        logger.debug("OCR 文字结构化处理完成")
        return result
