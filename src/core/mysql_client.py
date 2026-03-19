"""MySQL客户端模块"""
from typing import List, Dict, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from loguru import logger
from src.utils.config import get_settings


class MySQLClient:
    """MySQL客户端"""
    
    def __init__(self):
        """初始化MySQL客户端"""
        settings = get_settings()
        mysql_config = settings.mysql
        
        # 构建连接URL
        connection_url = (
            f"mysql+pymysql://{mysql_config.user}:{mysql_config.password}"
            f"@{mysql_config.host}:{mysql_config.port}/{mysql_config.database}"
            f"?charset=utf8mb4"
        )
        
        # 创建引擎
        self.engine = create_engine(
            connection_url,
            poolclass=QueuePool,
            pool_size=mysql_config.pool_size,
            max_overflow=mysql_config.max_overflow,
            pool_pre_ping=True,  # 连接前检查连接是否有效
            echo=False
        )
        
        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False
        )
        
        self.table_name = mysql_config.table_name
        logger.info(f"MySQL客户端初始化完成，表名: {self.table_name}")
    
    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    def fetch_batch(
        self,
        limit: int = 1000,
        last_processed_id: Optional[int] = None,
        where_clause: Optional[str] = None
    ) -> List[Dict]:
        """
        按 id 分批获取数据（用于断点续跑，避免大 OFFSET 性能问题）。

        Args:
            limit: 每批数量
            last_processed_id: 上一批已处理到的最大 id，本次取 id > last_processed_id；
                              None 表示从最小 id 开始
            where_clause: 额外的WHERE条件（不包含WHERE关键字）

        Returns:
            数据列表
        """
        session = self.get_session()
        try:
            where_condition = f"WHERE {where_clause}" if where_clause else ""
            if not where_condition:
                where_condition = "WHERE cover_link IS NOT NULL AND cover_link != ''"
            elif "cover_link" not in where_clause:
                where_condition += " AND cover_link IS NOT NULL AND cover_link != ''"
            if last_processed_id is not None:
                where_condition += " AND id > :last_processed_id"

            sql = text(f"""
                SELECT id, sku, isbn, cover_link, IFNULL(author, '') AS author
                FROM {self.table_name}
                {where_condition}
                ORDER BY id
                LIMIT :limit
            """)
            params = {"limit": limit}
            if last_processed_id is not None:
                params["last_processed_id"] = last_processed_id

            result = session.execute(sql, params)
            rows = result.fetchall()

            records = []
            for row in rows:
                records.append({
                    "id": row[0],
                    "sku": row[1] or "",
                    "isbn": row[2] or "",
                    "cover_link": row[3] or "",
                    "author": row[4] or "",
                })

            logger.info(
                f"从MySQL获取 {len(records)} 条记录，last_processed_id={last_processed_id}, limit={limit}"
            )
            return records

        except Exception as e:
            logger.error(f"MySQL查询失败: {e}")
            raise
        finally:
            session.close()
    
    def count_total(self, where_clause: Optional[str] = None) -> int:
        """
        获取总记录数
        
        Args:
            where_clause: 额外的WHERE条件
        
        Returns:
            总记录数
        """
        session = self.get_session()
        try:
            where_condition = f"WHERE {where_clause}" if where_clause else ""
            if not where_condition:
                where_condition = "WHERE cover_link IS NOT NULL AND cover_link != ''"
            elif "cover_link" not in where_clause:
                where_condition += " AND cover_link IS NOT NULL AND cover_link != ''"
            
            sql = text(f"""
                SELECT COUNT(*) as total
                FROM {self.table_name}
                {where_condition}
            """)
            
            result = session.execute(sql)
            total = result.scalar()
            
            logger.info(f"MySQL总记录数: {total}")
            return total
            
        except Exception as e:
            logger.error(f"MySQL计数失败: {e}")
            raise
        finally:
            session.close()
    
    def close(self):
        """关闭连接"""
        self.engine.dispose()
        logger.info("MySQL连接已关闭")
