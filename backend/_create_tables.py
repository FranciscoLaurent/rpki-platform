"""临时脚本：重建数据库表结构（同步方式）"""

import os
from pathlib import Path

from sqlalchemy import create_engine

from app.models import Base

# 使用相对路径，避免硬编码绝对路径
DB_PATH = str(Path(__file__).parent / "rpki_platform.db")


def main():
    # 删除旧数据库文件
    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)
            print(f"Removed {path}")

    # 使用同步引擎创建表
    sync_url = f"sqlite:///{DB_PATH}"
    engine = create_engine(sync_url, echo=False)
    Base.metadata.create_all(engine)
    print("Done: tables created")


if __name__ == "__main__":
    main()
