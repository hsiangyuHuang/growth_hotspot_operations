"""测试数据抓取 - 统计各信源热点条数"""
import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from fetcher import rss, twitter


async def main():
    print("=" * 60)
    print("开始测试数据抓取（过去 24 小时）")
    print("=" * 60)
    print()
    
    # 临时输出路径
    test_output = Path(__file__).parent / "test_output.json"
    test_output.parent.mkdir(exist_ok=True)
    
    # 清空之前的测试数据
    if test_output.exists():
        test_output.unlink()
    
    # 1. RSS 抓取
    print("📰 [1/2] 抓取 RSS 源...")
    rss_items = await rss.fetch_all(test_output)
    print(f"   ✓ RSS 总计: {len(rss_items)} 条\n")
    
    # 2. Twitter 抓取
    print("🐦 [2/2] 抓取 Twitter...")
    twitter_items = await twitter.fetch_all(test_output)
    print(f"   ✓ Twitter 总计: {len(twitter_items)} 条\n")
    
    # 读取所有数据
    with open(test_output, "r", encoding="utf-8") as f:
        all_items = json.load(f)
    
    # 统计分析
    print("=" * 60)
    print("📊 数据统计分析")
    print("=" * 60)
    print()
    
    # 按信源统计
    source_stats = defaultdict(int)
    lang_stats = defaultdict(int)
    
    for item in all_items:
        source_stats[item["source"]] += 1
        lang_stats[item["lang"]] += 1
    
    # 1. RSS 源统计
    print("📰 RSS 源统计:")
    print("-" * 60)
    rss_sources = {k: v for k, v in source_stats.items() if not k.startswith("twitter:")}
    for source, count in sorted(rss_sources.items(), key=lambda x: -x[1]):
        print(f"  {source:40s} {count:3d} 条")
    print()
    
    # 2. Twitter 账号统计
    print("🐦 Twitter 账号统计:")
    print("-" * 60)
    twitter_sources = {k: v for k, v in source_stats.items() if k.startswith("twitter:")}
    for source, count in sorted(twitter_sources.items(), key=lambda x: -x[1]):
        handle = source.replace("twitter:@", "")
        print(f"  @{handle:38s} {count:3d} 条")
    print()
    
    # 3. 语言分布
    print("🌍 语言分布:")
    print("-" * 60)
    for lang, count in sorted(lang_stats.items(), key=lambda x: -x[1]):
        lang_name = "中文" if lang == "zh" else "英文"
        percentage = count / len(all_items) * 100
        print(f"  {lang_name:10s} {count:3d} 条 ({percentage:.1f}%)")
    print()
    
    # 4. 时间分布（按小时）
    print("⏰ 时间分布（最近 24 小时）:")
    print("-" * 60)
    hour_stats = defaultdict(int)
    for item in all_items:
        pub_time = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
        hour = pub_time.strftime("%Y-%m-%d %H:00")
        hour_stats[hour] += 1
    
    for hour in sorted(hour_stats.keys(), reverse=True)[:8]:  # 显示最近 8 小时
        count = hour_stats[hour]
        bar = "█" * (count // 5)
        print(f"  {hour}  {count:3d} 条 {bar}")
    print()
    
    # 5. 总结
    print("=" * 60)
    print("📈 总结")
    print("=" * 60)
    print(f"  总条目数: {len(all_items)}")
    print(f"  RSS 源:   {len(rss_sources)} 个源，{sum(rss_sources.values())} 条")
    print(f"  Twitter:  {len(twitter_sources)} 个账号，{sum(twitter_sources.values())} 条")
    print(f"  中英比例: {lang_stats.get('zh', 0)}:{lang_stats.get('en', 0)}")
    print()
    
    # 6. 优化建议
    print("💡 优化建议:")
    print("-" * 60)
    
    # 检查低产出源
    low_output = [s for s, c in rss_sources.items() if c < 3]
    if low_output:
        print(f"  ⚠️  低产出 RSS 源（< 3 条）：{len(low_output)} 个")
        for source in low_output[:5]:
            print(f"      - {source} ({rss_sources[source]} 条)")
        if len(low_output) > 5:
            print(f"      ... 还有 {len(low_output) - 5} 个")
    
    # 检查高产出源
    high_output = [s for s, c in rss_sources.items() if c > 20]
    if high_output:
        print(f"  ✅ 高产出 RSS 源（> 20 条）：{len(high_output)} 个")
        for source in sorted(high_output, key=lambda s: -rss_sources[s])[:5]:
            print(f"      - {source} ({rss_sources[source]} 条)")
    
    # Twitter 活跃度
    inactive_twitter = [s for s, c in twitter_sources.items() if c < 3]
    if inactive_twitter:
        print(f"  ⚠️  低活跃 Twitter 账号（< 3 条）：{len(inactive_twitter)} 个")
        for source in inactive_twitter[:5]:
            handle = source.replace("twitter:@", "")
            print(f"      - @{handle} ({twitter_sources[source]} 条)")
        if len(inactive_twitter) > 5:
            print(f"      ... 还有 {len(inactive_twitter) - 5} 个")
    
    active_twitter = [s for s, c in twitter_sources.items() if c >= 15]
    if active_twitter:
        print(f"  ✅ 高活跃 Twitter 账号（≥ 15 条）：{len(active_twitter)} 个")
        for source in sorted(active_twitter, key=lambda s: -twitter_sources[s])[:5]:
            handle = source.replace("twitter:@", "")
            print(f"      - @{handle} ({twitter_sources[source]} 条)")
    
    # 语言平衡建议
    zh_ratio = lang_stats.get('zh', 0) / len(all_items) * 100
    if zh_ratio < 20:
        print(f"  💭 中文内容占比较低（{zh_ratio:.1f}%），建议增加中文信源")
    elif zh_ratio > 50:
        print(f"  💭 中文内容占比较高（{zh_ratio:.1f}%），建议增加英文信源")
    
    print()
    print(f"✅ 测试完成！数据已保存至: {test_output}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
