# 命理推演器 · 从这里开始

## 一分钟上手

1. **双击 `index.html`** —— 浏览器里浏览全部演示与源码
2. 想跑代码：
   ```bash
   cd source
   python3 -m mingli
   ```
   需要 Python 3.10+，零第三方依赖。

## 目录

```
mingli-project/
├── index.html          项目首页（双击打开）
├── source-code.html    全部源码，带行号高亮，浏览器里直接读
├── demos/              九个演示（盘面、调参滑杆、校准报告、案例对决）
└── source/
    ├── mingli/         19 个源文件
    │   ├── README.md   完整文档（649 行）
    │   ├── calendar.py 天文历法：儒略日、太阳黄经、节气、真太阳时
    │   ├── lunar.py    农历：朔、闰月
    │   ├── jiazi.py    符号层：干支、藏干、十神、纳音、长生
    │   ├── bazi.py     八字
    │   ├── ziwei.py    紫微斗数
    │   ├── liuyao.py   六爻（纳甲筮法）
    │   ├── meihua.py   梅花易数
    │   ├── qimen.py    奇门遁甲（时家转盘·拆补定局）
    │   ├── liuren.py   大六壬（四课三传）
    │   ├── rules.py    权重层：60+ 可调参数
    │   ├── web.py      调参页生成
    │   ├── calibrate.py 校准：案例反推权重 + 统计检验
    │   ├── caselog.py   案例库：预注册 + 防篡改哈希链
    │   ├── cli.py       命令行 + 交互模式
    │   └── tests.py     67 项回归测试
    └── output/         示例数据
```

## 快速命令

```bash
cd source

python3 -m mingli                     # 交互菜单（12 个功能）

# 七个引擎
python3 -m mingli bazi   --date "1990-06-15 10:30" --lng 116.4 --gender m
python3 -m mingli ziwei  --date "1990-06-15 10:30" --lng 116.4 --gender m
python3 -m mingli liuyao --coins 1,2,3,1,0,2 --date "2026-11-27 15:30" --ask 财
python3 -m mingli meihua --nums 37,82
python3 -m mingli qimen  --date "2026-11-27 15:30" --lng 116.4
python3 -m mingli liuren --date "2026-11-27 15:30" --lng 116.4
python3 -m mingli jieqi 2026

# 权重层
python3 -m mingli rules                          # 查看全部参数
python3 -m mingli slider --engine qimen --date "2026-11-27 15:30" --out x.html

# 校准与记录
python3 -m mingli calibrate --make-demo d.json --cases 60
python3 -m mingli calibrate --data d.json
python3 -m mingli log add --engine liuyao --coins 1,2,3,1,0,2 --ask 财
python3 -m mingli log stats
python3 -m mingli log compare --b classic
```

## 推送到 GitHub

```bash
cd source
git init && git add -A && git commit -m "命理推演器 v1"
git remote add origin https://github.com/yaoqianhao/mingli.git
git branch -M main && git push -u origin main
```

## 一句提醒

这是符号推演工具。它能保证「符号 → 符号」符合古法规则，
不能保证「符号 → 现实」的映射成立。

`calibrate` 和 `caselog` 两个模块就是为了检验后者而存在的，
它们给出的答案可能是否定的——那也是答案。

先读 `source/mingli/README.md`，每个引擎那节末尾都有「已知边界」。
