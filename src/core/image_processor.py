"""图片处理模块"""
import io
from typing import Tuple, Optional
from PIL import Image
import imagehash
import httpx
from loguru import logger
from src.utils.config import get_settings


class ImageProcessor:
    """图片处理器"""
    
    def __init__(self):
        """初始化图片处理器"""
        settings = get_settings()
        self.timeout = settings.processing.image_download_timeout
        logger.info("图片处理器初始化完成")
    
    def download_image(self, image_url: str) -> Optional[bytes]:
        """
        下载图片
        
        Args:
            image_url: 图片URL
        
        Returns:
            图片字节数据，失败返回None
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(image_url)
                response.raise_for_status()
                
                if response.status_code == 200:
                    logger.debug(f"图片下载成功: {image_url}")
                    return response.content
                else:
                    logger.warning(f"图片下载失败，状态码: {response.status_code}, URL: {image_url}")
                    return None
                    
        except httpx.TimeoutException:
            logger.error(f"图片下载超时: {image_url}")
            return None
        except Exception as e:
            logger.error(f"图片下载失败: {e}, URL: {image_url}")
            return None
    
    def validate_image(self, image_data: bytes) -> Tuple[Optional[Image.Image], Optional[str]]:
        """
        验证图片
        
        Args:
            image_data: 图片字节数据
        
        Returns:
            (图片对象, 错误信息)
        """
        try:
            # 读取图片
            img = Image.open(io.BytesIO(image_data))
            
            # 格式验证（支持 JPEG/JPG、PNG、WEBP，不区分大小写）
            allowed_formats = {'JPEG', 'JPG', 'PNG', 'WEBP'}
            fmt = (img.format or "").upper()
            if fmt not in allowed_formats:
                error_msg = f"不支持的格式: {img.format}"
                logger.warning(error_msg)
                return None, error_msg
            
            # 可读性验证
            img.verify()
            
            # 重新打开（verify后需要重新打开）
            img = Image.open(io.BytesIO(image_data))
            
            logger.debug(f"图片验证成功，格式: {img.format}, 尺寸: {img.size}")
            return img, None
            
        except Exception as e:
            error_msg = f"图片验证失败: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def calculate_hash(self, img: Image.Image) -> str:
        """
        计算感知哈希
        
        Args:
            img: 图片对象
        
        Returns:
            感知哈希字符串
        """
        try:
            phash = imagehash.phash(img)
            hash_str = str(phash)
            logger.debug(f"感知哈希计算成功: {hash_str}")
            return hash_str
        except Exception as e:
            logger.error(f"感知哈希计算失败: {e}")
            raise
    
    def process_image(self, image_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        处理图片：下载、验证、计算哈希
        
        Args:
            image_url: 图片URL
        
        Returns:
            (感知哈希, 错误信息)
        """
        # 1. 下载图片
        image_data = self.download_image(image_url)
        if image_data is None:
            return None, "图片下载失败"
        
        # 2. 验证图片
        img, error = self.validate_image(image_data)
        if img is None:
            return None, error or "图片验证失败"
        
        # 3. 计算感知哈希
        try:
            cover_hash = self.calculate_hash(img)
            return cover_hash, None
        except Exception as e:
            return None, f"感知哈希计算失败: {str(e)}"
