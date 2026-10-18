# pathvalidate 安全与健壮性审查报告

| 项目 | 值 |
|---|---|
| 上游仓库 | https://github.com/thombashi/pathvalidate |
| 审查提交 | `1ca0a50fce51d5b5bd633457a72abf74dbe3112d`（master，2026-05-10） |
| 版本 | 3.3.1 |
| 许可证 | MIT（Copyright 2016-2025, Tsuyoshi Hombashi）——原样保留，未修改 |
| 审查日期 | 2026-10-18 |
| 审查平台 | Windows 10/11 x64，CPython 3.12.10 / 3.13.14 / 3.14.5 |
| 结论 | 发现并修复 **3 个独立缺陷**（同一根因族 2 个 + 1 个独立逻辑缺陷），新增 40 个回归测试，上游测试套件 4184 → 4224 全绿 |

---

## 1. 为什么选这个项目

要求是"有实际使用价值的开源项目"。`pathvalidate` 每天被下游用来处理**来自外部的文件名**——上传文件改名、下载文件落盘、归档解包。它处于"不可信输入 → 文件系统"这条路径上，一旦净化结果与预期不符，后果直接落在磁盘上。296 stars、MIT、零运行时依赖、测试套件 4184 例，具备可验证条件。

审查维度对应关系：

| 要求维度 | 本次覆盖情况 |
|---|---|
| 输入校验 | ✅ 主要发现（替代文本未转义即当作正则模板） |
| 路径处理 | ✅ 主要发现（驱动器相对路径被改写为绝对路径） |
| 权限控制 | ⬜ 不适用：纯字符串库，不触碰权限位 |
| 资源释放 | ⬜ 不适用：无文件句柄/网络/子进程 |
| 超时与重试 | ⬜ 不适用：无 I/O 操作 |
| 依赖版本冲突 | ✅ 已查：`python_requires>=3.9`，零运行时依赖，无冲突面 |
| 操作系统差异 | ✅ 已验证：Windows 路径语义 + 3 个 CPython 版本 + 异常类名差异 |

未覆盖项并非跳过，而是该库架构上不存在对应面。报告第 7 节说明这一取舍。

---

## 2. 先说被排除的"疑似问题"

**不能只凭代码模式或扫描器就认定漏洞。** 以下四项经实测后被判定为"非缺陷"，未做修改：

### 2.1 净化器不保证输出有效 —— 维护者的明确设计取舍

`sanitize_filepath` 可以返回自身校验器拒绝的值（例如超长路径 #49、全部由点号组成的名字 #69）。初看像漏洞，但：

- 上游 issue [#49](https://github.com/thombashi/pathvalidate/issues/49) 与 [#69](https://github.com/thombashi/pathvalidate/issues/69) 已明确讨论并**关闭**；
- 维护者给出的补偿机制是 `validate_after_sanitize=True`，实测该开关确实会抛异常；
- 这是向后兼容的默认值选择，不是遗漏。

**处理：不修，不改默认行为。** 报告中列为已知限制（第 8 节）。

### 2.2 `universal` 平台下的"绝对路径"判定

`_filepath.py` 中有一段构造了 `ValidationError` 却没有 `raise` 的对象，静态阅读像是死代码。但实测证明它**不是**漏洞：该分支只是冗余，真正抛错的是后面构造的 `err_object`。行为正确，故不动。

> 这一条是本次审查中最重要的自我纠错：如果只看"构造了异常却没用"，会误报一个不存在的缺陷。

### 2.3 `..` 路径分量原样保留

`sanitize_filepath("../../etc/passwd")` 默认返回 `../../etc/passwd`。这是**既有且刻意**的行为——净化器不是安全边界，文档从未承诺消除路径穿越。因此本次修复**没有**顺手"加固"它（那会破坏大量合法相对路径用法），只在第 8 节提醒调用方必须自己做 containment 检查。

### 2.4 `replacement_text` 的字面替换语义

修复前必须先确认：没有内部代码依赖"正则模板"语义。`grep` 全部 `re.sub` 调用点 + 全仓搜索 `\g<0>`：零命中，文档与示例也从未提及模板能力。因此把替代文本当**字面量**处理不会破坏任何既有契约。

---

## 3. 缺陷 A：替代文本被当作正则替换模板

### 3.1 证据

```
>>> sanitize_filename("a?b", replacement_text="\\")
re.PatternError: bad escape (end of pattern) at position 0

>>> sanitize_filename("a?b", replacement_text="\\x00")
re.PatternError: bad escape \x at position 0

>>> sanitize_filename("a?b", replacement_text="x\\1")
re.PatternError: invalid group reference 1 at position 2
```

不抛异常的那几种更隐蔽 —— 它**静默改了字符**：

| `replacement_text` | 实际输出 | 输出字节 | 预期 |
|---|---|---|---|
| `"\\b"` | `'a\x08b'` | `[97, 8, 98]` | `a\bb`（退格符！） |
| `"\\t"` | `'a\tb'` | `[97, 9, 98]` | `a\tb`（制表符） |
| `"\\g<0>"` | `'a?b'` | `[97, 63, 98]` | **非法字符 `?` 被原样吐回，等于完全没净化** |
| `"\\\\"` | `'a\\b'` | `[97, 92, 98]` | 两个反斜杠只剩一个 |

### 3.2 根因

`re.sub(pattern, repl, text)` 的 `repl` 参数是**替换模板**，`re` 会解析其中的反斜杠转义与组引用。而 `replacement_text` 是调用方给的**普通文本**。代码把它直接传了进去：

```python
# 修复前（_filename.py:79）
sanitized_filename = self._sanitize_regexp.sub(replacement_text, str(value))
```

同一根因共 **6 处**：`_filename.py:79`、`_filename.py:88`（保留名重写）、`_filepath.py:95`、`_symbol.py:80`、`_symbol.py:88`、`_ltsv.py:44`，外加 `_common.py` 的 `replace_unprintable_char` / `replace_ansi_escape`。

### 3.3 为什么这不只是"报错难看"

两个层面：

1. **错误契约被破坏。** 函数文档写明 `Raises: ValueError`，`ValidationError` 也确实是 `ValueError` 子类。但 `re.error` 的 MRO 是 `Exception → BaseException`，**不是** `ValueError`。调用方写 `except ValueError`（按文档来）会直接漏接，进程崩掉。
2. **跨版本行为不一致。** 同一个异常在不同解释器上的类名不同：

   | CPython | 异常类名 | `isinstance(e, ValueError)` |
   |---|---|---|
   | 3.12 | `re.error` | False |
   | 3.13 | `re.PatternError` | False |
   | 3.14 | `re.PatternError` | False |

   任何靠异常名做分派的调用方（日志分类、重试判定）都会在升级解释器时静默失灵。

3. **净化可被完全旁路。** `replacement_text="\g<0>"` 让替换内容等于原匹配内容，净化为空操作：

   ```
   sanitize_filename("a?b", replacement_text="\\g<0>")  ->  'a?b'
   is_valid_filename('a?b')                              ->  False
   ```

   此时把结果 `os.path.join(upload_dir, ...)` 落盘，`?` 在 Windows 上是非法字符。

### 3.4 触发条件与严重性判定

**必须诚实说明**：`replacement_text` 是**调用方**参数，不是被净化的输入。因此：

- 攻击者不能只靠构造文件名触发；
- 只有当下游应用把用户可控数据传进 `replacement_text`（少见，但确有此类封装），或使用含反斜杠的替换符（如 `"\\"`、`"\\\\"`，在 Windows 场景并非天方夜谭）时才会踩中。

因此本次**不宣称**这是远程可利用漏洞。它的准确定性是：**公开 API 的错误处理契约缺陷 + 净化语义缺陷**，影响所有传非平凡替代文本的调用方，并造成跨解释器不可移植。第 3.3 节第 3 点是它为什么会落在磁盘上的具体路径。

### 3.5 修复

新增 `_common.escape_replacement_text()`，把反斜杠加倍后再交给 `re.sub`，使其严格按字面量插入：

```python
def escape_replacement_text(replacement_text: str) -> str:
    if not replacement_text:
        return replacement_text
    return replacement_text.replace("\\", "\\\\")
```

空串短路，保证默认路径（`replacement_text=""`）只多一次真值判断。6 个调用点全部接入。

**为什么用转义而不是 `lambda m: repl`**：`lambda` 语义同样正确，但每次匹配多一次 Python 函数调用；转义是纯字符串操作，且保持原有 `re.sub` 调用形态，改动面最小。

---

## 4. 缺陷 B：驱动器相对路径被静默改写为绝对路径

### 4.1 证据

```
>>> sanitize_filepath("C:x.txt", platform="windows")
'C:\\x.txt'          # 输入是相对路径，输出变成了绝对路径
```

`ntpath.splitdrive("C:x.txt")` 返回 `("C:", "x.txt")`。原代码把 drive 与分隔符拼回去，`C:` + `\\` + `x.txt` = `C:\x.txt` —— **绝对路径**。

### 4.2 后果一：`os.path.join` 的基目录被吞掉

这是本次审查里唯一能直接落到文件系统越界的一点。Python 的 `os.path.join` 在遇到绝对路径的第二个参数时会**丢弃第一个参数**：

```
BASE = r"C:\srv\uploads"
sanitize_filepath("D:payload.exe", platform="windows")  ->  'D:payload.exe' （修复后）
```

修复前实际发生的是：

| 输入（相对） | 修复前净化结果 | `os.path.join(BASE, out)` | 结论 |
|---|---|---|---|
| `C:x.txt` | `C:\x.txt` | `C:\x.txt` | 逃出 BASE |
| `C:file.txt` | `C:\file.txt` | `C:\file.txt` | 逃出 BASE |
| `D:payload.exe` | `D:\payload.exe` | `D:\payload.exe` | 逃出 BASE（换盘） |
| `C:..\..\evil.txt` | `C:\..\..\evil.txt` | `C:\evil.txt` | 逃出 BASE |

一个本应写入上传目录的相对名，变成了向任意盘符根目录写入的绝对路径。

### 4.3 后果二：valid-in / invalid-out 契约自相矛盾

`validate_filepath` **接受** `C:x.txt`，但 `sanitize_filepath` 会把它变成 `validate_filepath` **拒绝**的东西：

| 平台 | 输入 | `validate(in)` | 净化结果 | `validate(out)` |
|---|---|---|---|---|
| universal | `C:x.txt` | ACCEPT | `C:/x.txt` | **REJECT PV1201** |
| universal | `D:payload.exe` | ACCEPT | `D:/payload.exe` | **REJECT PV1201** |
| universal | `C:..\..\evil.txt` | ACCEPT | `C:/../../evil.txt` | **REJECT PV1201** |

并且开启严格模式后，函数会对自己刚产出的值抛异常 —— 自我矛盾：

```
>>> sanitize_filepath("C:x.txt", platform="universal", validate_after_sanitize=True)
ValidationError: [PV1201] found a malformed absolute path
```

这一条**不受 2.1 节的"设计取舍"豁免**：那不是长度或严格度问题，而是净化器把合法输入改坏了。

### 4.4 修复

在拆分 drive 后判定是否为驱动器相对形态（drive 非空、剩余部分非空、且不以分隔符开头），若是则不插入分隔符，改为把 drive 直接前缀拼接：

```python
is_drive_relative = bool(drive) and bool(unicode_filepath)
if is_drive_relative:
    is_drive_relative = unicode_filepath[0] not in ("/", "\\")
...
if drive and not is_drive_relative:
    sanitized_entries.append(drive)
...
if drive and is_drive_relative:
    sanitized_path = drive + sanitized_path
```

绝对路径（`C:\x.txt`、`C:/x.txt`、UNC `\\srv\share`）路径**完全不变**，由回归测试锁定。

---

## 5. 缺陷 C：连续字符折叠对多字符替代文本失效

### 5.1 证据

`replace_symbol(..., is_replace_consecutive_chars=True)` 声称把连续替代字符合并成一个。单字符有效，多字符无效：

```
>>> replace_symbol("a---b", "-",  is_replace_consecutive_chars=True)
'a-b'                      # 正确
>>> replace_symbol("a---b", "ab", is_replace_consecutive_chars=True)
'aababab'                  # 错：应当折叠为 'aab'
```

### 5.2 根因

```python
# 修复前（_symbol.py:88）
re.sub(f"{re.escape(replacement_text)}+", replacement_text, new_text)
```

`f"{re.escape('ab')}+"` 得到 `ab+` —— `+` 只作用于最后的 `b`，不是整个 `ab`。所以模式永远匹配不到 `abab` 这样的连续重复：

| 替代文本 | 生成模式 | 文本 | 匹配结果 | 正确模式 | 正确结果 |
|---|---|---|---|---|---|
| `ab` | `ab+` | `ababab` | `['ab','ab','ab']` | `(?:ab)+` | `['ababab']` |
| `a.b` | `a\.b+` | `a.ba.ba.b` | `['a.b','a.b','a.b']` | `(?:a\.b)+` | `['a.ba.ba.b']` |

### 5.3 为什么归入本次修复

这个缺陷独立于 A/B，但它与前两处**位于同一函数、同类"正则表达式构造错误"**，且上游 4 个已有测试全部只用单字符 `_` 做替代符（`test_symbol.py`），因此长期未被发现。修复 A 时会重写这一行，留着旧模式会让"替代文本按字面量处理"的语义不完整。附带修掉，并补齐多字符回归测试。

### 5.4 修复

```python
new_text = re.sub(
    f"(?:{re.escape(replacement_text)})+",
    escape_replacement_text(replacement_text),
    new_text,
)
```

---

## 6. 修改清单

### 6.1 源码（5 文件，+73 / −13 行）

| 文件 | 改动 |
|---|---|
| `pathvalidate/_common.py` | 新增 `escape_replacement_text()`；`replace_unprintable_char` / `replace_ansi_escape` 接入 |
| `pathvalidate/_filename.py` | 净化主流程（第 79 行）+ 保留名重写（第 88 行）接入转义 |
| `pathvalidate/_filepath.py` | 净化主流程接入转义；新增驱动器相对路径判定与前缀拼接 |
| `pathvalidate/_symbol.py` | `replace_symbol` 两处接入转义；连续折叠加非捕获分组 |
| `pathvalidate/_ltsv.py` | `sanitize_ltsv_label` 接入转义 |

### 6.2 测试（5 文件，+224 行，40 个新用例）

| 文件 | 新增类 / 用例 | 覆盖 |
|---|---|---|
| `test/test_common.py` | `Test_escape_replacement_text` | 转义函数本身 + 字面量插入 + 不抛 `re.error` |
| `test/test_filename.py` | `test_normal_reserved_name_handler_literal` | 保留名重写路径不误解析反斜杠 |
| `test/test_filepath.py` | `Test_sanitize_filepath_drive_relative` | 相对性保持 / valid-in-valid-out / 绝对路径不回归 |
| `test/test_symbol.py` | `Test_replace_symbol_replacement` | 字面量插入 + 多字符连续折叠 |
| `test/test_ltsv.py` | `Test_sanitize_ltsv_label_replacement` | 字面量插入 + 不抛 `re.error` |

逐文件明细（可用于核对交付物未被篡改）：

| 文件 | +行 | −行 | 交付后行数 | 交付 sha1(前12) |
|---|---:|---:|---:|---|
| `pathvalidate/_common.py` | 26 | 2 | 187 | `f769cf389bb5` |
| `pathvalidate/_filename.py` | 14 | 3 | 489 | `629b6980a2ec` |
| `pathvalidate/_filepath.py` | 20 | 3 | 533 | `e179190ea6c5` |
| `pathvalidate/_ltsv.py` | 2 | 2 | 44 | `7ef06982e468` |
| `pathvalidate/_symbol.py` | 11 | 3 | 101 | `c0beda40f3a6` |
| `test/test_common.py` | 54 | 0 | 113 | `527b01636c60` |
| `test/test_filename.py` | 23 | 0 | 833 | `b4f48d4096e3` |
| `test/test_filepath.py` | 71 | 0 | 1029 | `b62d35d6ca0a` |
| `test/test_ltsv.py` | 20 | 0 | 121 | `d95334ebd572` |
| `test/test_symbol.py` | 56 | 0 | 198 | `724a7187698c` |
| **合计** | **297** | **13** | | |

**没有新建测试文件**：上游 `test/map.js` 类的一一对应约束虽不存在于本项目，但仍遵循"测试放在对应模块的既有测试文件内"的约定，避免破坏测试发现结构。

### 6.3 未改动

- `LICENSE`、`__version__.py` 版权头、`__author__`：全部原样保留（MIT 要求）。
- 默认参数、公开签名、返回值类型：零变更，属 drop-in 兼容。
- 未新增任何运行时依赖。

---

## 7. 测试证据

### 7.1 上游套件：无回归

| 状态 | 结果 |
|---|---|
| 基线（`1ca0a50` 原始代码） | **4184 passed**, 14 skipped |
| 打补丁后 | **4224 passed**, 14 skipped |
| 差值 | +40，恰好等于新增用例数，**无一条既有测试被改或删除** |

### 7.2 反向喂毒：新测试在基线上必须失败

只证明"打完补丁是绿的"没有意义 —— 要证明测试能**抓住**缺陷。把补丁 stash 掉、在原始代码上跑新增用例：

```
24 failed, 4 passed    （escape / drive / absolute 相关）
```

失败的 24 条包含行为级断言（`assert sanitize_filename(...) == expected`），**不是** `ImportError` 之类的伪失败。

### 7.3 变异测试：9/9 全杀

逐个把修复改回错误形态，确认测试会红：

| # | 变异 | 结果 |
|---|---|---|
| M1 | 转义函数退化为 identity | KILLED |
| M2 | 只转义 `\g` 前缀 | KILLED |
| M3 | 关闭驱动器相对判定 | KILLED |
| M4 | 丢弃 drive 前缀 | KILLED |
| M5 | drive 一律当绝对路径（原始 bug） | KILLED |
| M6 | 连续折叠不加分组（原始 bug） | KILLED |
| M7 | filename 净化不再转义 | KILLED |
| M8 | ltsv 净化不再转义 | KILLED |
| M9 | 保留名重写不再转义 | **SURVIVED → 补测试 → KILLED** |

> M9 第一轮存活，暴露了真实盲区：`reserved_name_handler` 返回含反斜杠的字符串这条路径没有测试。补上 `test_normal_reserved_name_handler_literal` 后 9/9。
> **第一轮全绿不可信** —— 这条正是靠"变异存活"才发现的。

### 7.4 差分等价性

以独立参照实现 `re.sub(pattern, lambda m: repl, text)`（按定义即字面替换）作为 oracle，随机 3000 组输入 × 替代文本：

- `sanitize_filename` / `replace_symbol` / `sanitize_ltsv_label` **零差异**；
- 40 条初判差异经追查全部是 oracle 未建模 LTSV 的空白预校验（`' '` 会先被 `validate_pathtype` 拒绝），属 oracle 缺陷，非产品缺陷。

### 7.5 跨版本 / 跨平台

`../audit/cross_version_check.py`（零第三方依赖，可在任意解释器直跑）。脚本会**强制把同目录包置于 `sys.path` 首位，并打印实际解析到的文件路径**，避免误测机器上已安装的旧副本（本机 3.14 的 site-packages 里就有一份未打补丁的 3.3.1，早期一轮测量曾误命中它）：

| 解释器 | 实际导入 | 结果 |
|---|---|---|
| CPython 3.12.10 (win32) | `<deliverable>/pathvalidate/__init__.py` | all checks passed |
| CPython 3.13.14 (win32) | `<deliverable>/pathvalidate/__init__.py` | all checks passed |
| CPython 3.14.5 (win32) | `<deliverable>/pathvalidate/__init__.py` | all checks passed |

反向验证（`../audit/verify_against_installed.py`，把导入强制指向**未打补丁**的原始包）：

| 被测副本 | 结果 |
|---|---|
| 基线原版（未打补丁） | **崩溃**：`re.error: bad escape (end of pattern) at position 0` |
| 交付副本（已修复） | all checks passed |

即：同一脚本能区分"修好"与"没修"，不是恒绿的空断言。

> 交叉踩坑记录：早期一轮 `py -3.14` 报告 "all passed"，但实际导入的是 site-packages 里的**未打补丁**副本 —— 该副本因为从交付目录继承不到 `sys.path` 而加载了错的代码。加上"打印并校验解析路径"后才排除。**跨解释器验证必须先证明被测对象是哪一个。**

### 7.6 静态检查

| 检查 | 结果 |
|---|---|
| `ruff check --select E4,E7,E9,F`（CI 子集） | All checks passed |
| `ruff format --check`（全仓 25 文件） | 全部已格式化 |
| `mypy --python-version 3.10 pathvalidate` | Success: no issues found in 14 source files |
| 与基线 diff 的新增 lint 问题 | **0**（对 118 条既有告警做了基线差分，未新增、未顺手改无关文件） |

> 说明：本机 ruff 为 0.17.1，比上游 CI 钉的 `>=0.8` 新，对未改动代码报出 118 条既有告警。**我没有去"修"它们**，而是做基线差分证明自己零新增 —— 避免把无关改动混进交付。

### 7.7 性能

先说结论可靠性：本机为共享 Windows 工作机，A/A 噪声底（两份字节相同的代码对比）实测 **0.881 – 1.314**，比任何可能的效应都宽。因此**不给点值**，改用确定性指标：

| 指标 | 值 |
|---|---|
| 新增 `escape_replacement_text()` 空串路径 | 46.5 ns/次 |
| 非空单字符 | 62.8 ns/次 |
| 含反斜杠 | 79.2 ns/次 |
| 单次 `sanitize_filename` 调用量级 | ~18–21 µs |

即默认路径新增开销约 **0.25%**，且该函数只在净化时调用一次，未进入任何热循环。A/B 交错测量（9 轮、每轮独立子进程）比值落在 `0.94–1.09`，完全被噪声覆盖，**不宣称有性能影响**。

### 7.8 补丁可还原性

`../fixes.patch`（17 584 字节、18 个 hunk）在一份**从 git blob 重建的纯净 LF 上游**上 `patch -p1 --binary`：

- 10 个文件全部应用成功，0 reject；
- 逐文件 sha1 与交付副本**完全一致**（10/10）；
- 交付副本逐文件与上游 blob 比对：**86 个文件逐字节相同**，差异仅限我改的 10 个。

---

## 8. 尚未解决的风险

诚实列出，均为**已知且刻意不修**或**超出本库职责**：

### 8.1 净化器不是安全边界（严重度：高，责任在调用方）

修复后 `sanitize_filepath("../../etc/passwd")` 仍返回 `../../etc/passwd`。任何"把不可信名字拼到目录下"的代码**必须**自己做 containment 校验：

```python
dest = os.path.realpath(os.path.join(base, sanitize_filepath(name, platform="auto")))
if os.path.commonpath([dest, os.path.realpath(base)]) != os.path.realpath(base):
    raise ValueError("path escapes base directory")
```

本次修复消除了"本应相对却被改成绝对"这一类绕过，但**没有也不可能**把该库变成路径穿越防护层。

### 8.2 默认不保证输出有效（严重度：中，上游设计取舍）

`validate_after_sanitize` 默认 `False`，故超长路径、全点号名字等仍可能产出无效值（#49/#69）。上游计划在 v4 改默认值。调用方若需要强保证，必须显式开启该参数或自行复验。

### 8.3 `replacement_text` 仍可被恶意用于"取消净化"（严重度：低，语义使然）

修复后 `replacement_text` 是纯字面量，但它依然会被**原样插入**。传 `replacement_text="?"` 就能让 `a?b` 变成 `a?b?`（仍非法）。这不是转义能解决的问题 —— **替代文本必须是可信的**。若下游需要把用户数据用作替代符，应自行白名单过滤。

### 8.4 非 UTF-8 文件系统编码会抛 `UnicodeEncodeError`（严重度：低，既有行为）

```
>>> sanitize_filename("éé", fs_encoding="ascii")
UnicodeEncodeError: 'ascii' codec can't encode characters in position 0-1
```

`validate_filepath` 同样如此。这是 `truncate_str` 与长度计算直接调用 `.encode()` 的结果，未被包装进 `ValidationError`。属既有行为、与本次三个缺陷无关，**未修**（修它会改变异常类型，需要单独的兼容性决策）。建议上游统一包成 `ValidationError`。

### 8.5 仅验证 Windows 宿主（严重度：中，验证面限制）

所有实测均在 win32 上完成。Linux/macOS 的宿主差异（`sys.getfilesystemencoding()` 返回值、`os.path.normpath` 对反斜杠的处理）**未经真实机器验证**；但相关逻辑通过显式 `platform=` 参数做了平台无关的断言，且 `cross_version_check.py` 覆盖了 universal/windows 两种路径语义。建议上游 CI（Linux/macOS matrix）跑一遍确认。

### 8.6 未做模糊测试 / 未验证真实下游

- 未对 18075 组输入做完整属性测试（仅做了 round-trip 与差分）；
- 未在真实上传服务中验证端到端影响（第 4.2 节的越界结论基于 `os.path.join` 语义推导 + 直接复现，非线上复现）。

### 8.7 未向上游提交 PR

本次为离线审查 + 本地修复，未向上游发 PR/issue。若需上游采纳，建议按缺陷 A/B/C 拆成 3 个独立 PR，并附本报告的复现脚本。

---

## 9. 复现步骤

```bash
# 1. 解压交付 ZIP，安装测试依赖
cd pathvalidate-audit-2026-10-18
python -m venv .venv && .venv/Scripts/pip install -e . pytest allpairspy click Faker tcolorpy

# 2. 全量测试（应 4224 passed, 14 skipped）
.venv/Scripts/python -m pytest test -q

# 3. 跨版本行为检查（3.12 / 3.13 / 3.14 均可，会打印实际导入路径）
python audit/cross_version_check.py

# 3b. 反向验证：把导入强制指向一份未打补丁的副本，应崩溃
python audit/verify_against_installed.py <unpatched_dir> audit/cross_version_check.py --allow-external

# 4. 变异测试（应 9/9 killed；需先用 PATHVALIDATE_PY 指定带 pytest 的解释器）
PATHVALIDATE_PY=/path/to/python-with-pytest python audit/mutation_test.py

# 5. 在纯净上游上验证补丁
git clone https://github.com/thombashi/pathvalidate && cd pathvalidate
git checkout 1ca0a50
patch -p1 --binary < ../pathvalidate-audit-2026-10-18/fixes.patch
```

---

## 10. 一句话总结

选了一个"不可信文件名 → 磁盘"链路上的库，找到 3 处能改变实际落盘结果的缺陷（其中一处会把相对名变成绝对名从而吞掉基目录），全部实测复现、最小化修复、40 个回归测试锁定、9/9 变异全杀、3 个解释器验证；同时明确排除了 4 项"看着像漏洞其实是设计取舍"的误报。
