"""
Metal Price Report — 主入口。

编排完整的数据采集 → 处理 → 分析 → 报告生成流程。
"""

import os
from dotenv import load_dotenv


def main():
    """主流程入口。"""
    load_dotenv()
    print("Metal Price Report — 项目骨架已就绪。")


if __name__ == "__main__":
    main()
