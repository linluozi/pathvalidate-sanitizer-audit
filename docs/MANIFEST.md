# 交付物清单

**交付包：** `pathvalidate-audit-2026-10-18.zip`
**文件数：** 110（含本文件；校验值见随包 `SHA256SUMS.txt`）

> 压缩包自身的 SHA-256 记录在同级目录的 `SHA256SUMS.txt` 中 —— 本文件位于包内，
> 无法自指其所在包的哈希，因此不在此处写死数字，避免给出一个无法自洽的校验值。

## 内容结构

```
pathvalidate-audit-2026-10-18/
├── AUDIT_REPORT.md          问题分析、修复理由、测试证据、未解决风险
├── NOTICE.md                修改声明 + 上游版权/许可说明
├── fixes.patch              全部改动的 unified diff（18 hunk）
├── MANIFEST.md              本清单
├── LICENSE                  上游 MIT 许可证，原样未改
│
├── pathvalidate/            源码（5 个文件已修改，其余逐字节等同上游）
├── test/                    上游测试套件 + 40 个新增回归用例
├── docs/  examples/  requirements/ ...   上游其余文件，逐字节未改
├── pyproject.toml  setup.py  tox.ini ... 上游构建配置，逐字节未改
│
└── audit/                   本次审查新增的验证脚本（MIT，原创）
    ├── cross_version_check.py        跨解释器行为断言（零依赖，强制校验导入路径）
    ├── verify_against_installed.py   把导入指向指定副本，用于反向验证
    ├── mutation_test.py              9 个变异，验证测试能否抓住回归
    ├── probe_roundtrip.py            sanitize→validate 往返一致性
    ├── probe_swallow.py              枚举被静默吞掉的校验失败
    ├── probe_repl.py                 替代文本模板问题的根因定位
    ├── probe_drive.py                驱动器相对路径改写为绝对路径
    ├── probe_contract.py             valid-in / invalid-out 契约矛盾
    ├── probe_universal.py            universal 平台绝对路径判定（已排除的误报）
    └── bench_aa.py                   A/A 噪声底测量（说明为何不给计时点值）
```

## 快速校验

```bash
# 1. 全量测试
python -m pytest test -q          # 期望 4224 passed, 14 skipped

# 2. 跨解释器
python audit/cross_version_check.py    # 期望 all cross-version checks passed

# 3. 变异测试（需带 pytest 的解释器）
PATHVALIDATE_PY=$(which python) python audit/mutation_test.py   # 期望 9/9 killed

# 4. 补丁可还原性
git clone https://github.com/thombashi/pathvalidate && cd pathvalidate
git checkout 1ca0a50
patch -p1 --binary < ../pathvalidate-audit-2026-10-18/fixes.patch
```

## 完整性

- 上游 96 个受版本控制文件中，**86 个与基线 commit 的 blob 逐字节相同**；
- 其余 10 个即本次修改文件，逐一列于 `AUDIT_REPORT.md` §6.2 并附 sha1；
- `../fixes.patch` 应用于纯净 LF 上游后，产出的 10 个文件与交付副本 sha1 完全一致。
