"""测试 Twitter 数据抓取 - 输出 Markdown 格式"""
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from fetcher import twitter


async def main():
    print("=" * 80)
    print("开始抓取 Twitter 数据（过去 24 小时）")
    print("=" * 80)
    print()
    
    # 临时输出路径
    test_output = Path(__file__).parent / "test_twitter_output.json"
    
    # 清空之前的测试数据
    if test_output.exists():
        test_output.unlink()
    
    # 抓取 Twitter
    print("🐦 抓取 Twitter 数据...")
    items = await twitter.fetch_all(test_output)
    print(f"✓ 总计: {len(items)} 条推文\n")
    
    if not items:
        print("⚠️  没有抓取到数据，请检查 TWITTER_API_KEY 环境变量")
        return
    
    # 读取数据
    with open(test_output, "r", encoding="utf-8") as f:
        all_items = json.load(f)
    
    # 按账号分组
    by_account = {}
    for item in all_items:
        handle = item["source"].replace("twitter:@", "")
        if handle not in by_account:
            by_account[handle] = []
        by_account[handle].append(item)
    
    # 生成 Markdown
    md_output = Path(__file__).parent / "twitter_data.md"
    
    with open(md_output, "w", encoding="utf-8") as f:
        f.write("# Twitter 数据抓取报告\n\n")
        f.write(f"**抓取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**时间范围**: 过去 24 小时\n\n")
        f.write(f"**总推文数**: {len(all_items)} 条\n\n")
        f.write(f"**账号数**: {len(by_account)} 个\n\n")
        f.write("---\n\n")
        
        # 统计表格
        f.write("## 📊 账号统计\n\n")
        f.write("| 账号 | 推文数 |\n")
        f.write("|------|--------|\n")
        for handle in sorted(by_account.keys(), key=lambda h: -len(by_account[h])):
            count = len(by_account[handle])
            f.write(f"| @{handle} | {count} |\n")
        f.write("\n---\n\n")
        
        # 按账号展示推文
        f.write("## 📝 推文详情\n\n")
        
        for handle in sorted(by_account.keys()):
            tweets = by_account[handle]
            f.write(f"### @{handle}\n\n")
            f.write(f"**推文数**: {len(tweets)}\n\n")
            
            # 按时间倒序排列
            tweets_sorted = sorted(tweets, key=lambda t: t["published_at"], reverse=True)
            
            for i, tweet in enumerate(tweets_sorted, 1):
                pub_time = datetime.fromisoformat(tweet["published_at"].replace("Z", "+00:00"))
                pub_str = pub_time.strftime("%Y-%m-%d %H:%M")
                
                f.write(f"#### {i}. {pub_str}\n\n")
                
                # 标题（前100字符）
                if tweet["title"]:
                    f.write(f"**{tweet['title']}**\n\n")
                
                # 完整内容
                content = tweet["content"]
                if content:
                    # 处理换行
                    content_formatted = content.replace("\n", "\n> ")
                    f.write(f"> {content_formatted}\n\n")
                
                # 链接
                f.write(f"🔗 [查看推文]({tweet['url']})\n\n")
                
                # 字符统计
                char_count = len(content)
                f.write(f"*字符数: {char_count}*\n\n")
                
                if i < len(tweets_sorted):
                    f.write("---\n\n")
            
            f.write("\n")
    
    print(f"✅ Markdown 报告已生成: {md_output}")
    print()
    
    # 输出摘要到控制台
    print("=" * 80)
    print("📊 数据摘要")
    print("=" * 80)
    print()
    
    for handle in sorted(by_account.keys(), key=lambda h: -len(by_account[h])):
        count = len(by_account[handle])
        print(f"  @{handle:30s} {count:3d} 条")
    
    print()
    print(f"查看完整报告: {md_output}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
