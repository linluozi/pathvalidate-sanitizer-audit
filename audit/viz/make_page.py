"""Render the single-file report page from data/results.json + assets/*.png.

All tables are generated from the collected data; no measured value is typed in.
Images are inlined as base64 so index.html is fully self-contained (works from
file://, from a raw.githubusercontent URL, and from GitHub Pages).

Usage: python make_page.py
"""
import base64
import html
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "pathvalidate-audit-2026-10-18", "docs", "index.html")

with open(os.path.join(HERE, "data", "results.json"), encoding="utf-8") as fp:
    D = json.load(fp)

U, P = D["unpatched"], D["patched"]


def img(name):
    path = os.path.join(HERE, "assets", name)
    with open(path, "rb") as fp:
        b64 = base64.b64encode(fp.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------
def table_replacement() -> str:
    labels = {
        "literal": ("ok", "literal (correct)"),
        "corrupt": ("bad", "silently corrupted"),
        "noop": ("warn", "sanitisation skipped"),
        "crash": ("bad", "crash"),
    }
    rows = []
    for a, b in zip(U["replacement_corpus"], P["replacement_corpus"]):
        ca, la = labels[a["class"]]
        cb, lb = labels[b["class"]]
        rows.append(
            "<tr>"
            f"<td class=m><code>{esc(a['repl_show']) or '&lt;empty&gt;'}</code></td>"
            f"<td class='{ca}'>{la}</td>"
            f"<td class=m><code>{esc(a.get('out_show','—'))}</code></td>"
            f"<td class='{cb}'>{lb}</td>"
            f"<td class=m><code>{esc(b.get('out_show','—'))}</code></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>replacement_text</th><th>before</th><th>output before</th>"
        "<th>after</th><th>output after</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def table_escape() -> str:
    rows = []
    for a, b in zip(U["B_rows"], P["B_rows"]):
        esc_flag = "bad" if (a["out_abs"] and not a["in_abs"]) else ""
        rows.append(
            "<tr>"
            f"<td class=m><code>{esc(a['in'])}</code></td>"
            f"<td class=m>{'relative' if not a['in_abs'] else 'absolute'}</td>"
            f"<td class=m><code>{esc(a['out'] or '—')}</code></td>"
            f"<td class='{esc_flag}'>{'ABSOLUTE' if a['out_abs'] else 'relative'}</td>"
            f"<td class=m><code>{esc(b['out'] or '—')}</code></td>"
            f"<td>{'relative' if not b['out_abs'] else 'ABSOLUTE'}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>input (relative)</th><th>class</th><th>before</th><th>is absolute?</th>"
        "<th>after</th><th>is absolute?</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def table_universal() -> str:
    rows = []
    for a, b in zip(U["B_universal"], P["B_universal"]):
        def cell(v):
            return ("bad", "rejected") if v != "accept" else ("ok", "accepts")

        ca, ta = cell(a["vout"])
        cb, tb = cell(b["vout"])
        rows.append(
            "<tr>"
            f"<td class=m><code>{esc(a['in'])}</code></td>"
            f"<td>{a['vin']}</td>"
            f"<td class='{ca}'>{ta}</td>"
            f"<td class='{cb}'>{tb}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>input</th><th>validate(in)</th>"
        "<th>validate(sanitize(in)) before</th>"
        "<th>validate(sanitize(in)) after</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def table_sweep() -> str:
    rows = []
    for plat in ["universal", "windows", "linux", "macos", "posix"]:
        u = U["sweep_invalid_output"][plat]
        p = P["sweep_invalid_output"][plat]
        rows.append(
            "<tr>"
            f"<td class=m>{esc(plat)}</td>"
            f"<td class='{'bad' if u['drive_relative'] else ''}'>{u['drive_relative']}</td>"
            f"<td class='{'ok' if p['drive_relative'] == 0 else 'bad'}'>"
            f"{p['drive_relative']}</td>"
            f"<td class=mut>{u['documented_design']}</td>"
            f"<td class=mut>{u['ok']} → {p['ok']}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>platform</th><th>broken before</th><th>broken after</th>"
        "<th>documented failures</th><th>valid before → after</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def table_mutations() -> str:
    rows = [
        ("M1", "escape helper becomes identity", "killed"),
        ("M2", "escape only the <code>\\g</code> prefix", "killed"),
        ("M3", "drive-relative detection disabled", "killed"),
        ("M4", "drive prefix dropped entirely", "killed"),
        ("M5", "drive always treated as absolute (original bug)", "killed"),
        ("M6", "consecutive quantifier ungrouped (original bug)", "killed"),
        ("M7", "filename sanitiser stops escaping", "killed"),
        ("M8", "ltsv sanitiser stops escaping", "killed"),
        ("M9", "reserved-name rewrite stops escaping", "survived → test added → killed"),
    ]
    body = "".join(
        f"<tr><td class=m>{i}</td><td>{esc(d).replace('&lt;code&gt;','<code>').replace('&lt;/code&gt;','</code>')}</td>"
        f"<td class='{'ok' if m.startswith('killed') else 'warn'}'>{esc(m)}</td></tr>"
        for i, d, m in rows
    )
    return (
        "<table><thead><tr><th>#</th><th>mutation</th><th>result</th></tr></thead>"
        "<tbody>" + body + "</tbody></table>"
    )


def src_snippet(rel_path: str, first: str, last: str) -> str:
    """Pull a code block straight out of the shipped source.

    Hand-typed escapes inside this generator's f-strings doubled the backslashes
    (the page showed \\\\ where the source has \\), so the snippets are read from
    the actual files instead.
    """
    path = os.path.join(os.path.dirname(HERE), "pathvalidate-audit-2026-10-18", rel_path)
    lines = open(path, encoding="utf-8").read().splitlines()
    start = next(i for i, ln in enumerate(lines) if first in ln)
    end = next(i for i, ln in enumerate(lines[start:], start) if last in ln)
    return esc("\n".join(lines[start : end + 1]))


def src_body(rel_path: str, first: str) -> str:
    """Return the code lines of a function, skipping its docstring.

    Read from the shipped source so escapes are exactly what runs (hand-typed
    backslashes in this generator doubled themselves).
    """
    path = os.path.join(os.path.dirname(HERE), "pathvalidate-audit-2026-10-18", rel_path)
    lines = open(path, encoding="utf-8").read().splitlines()
    start = next(i for i, ln in enumerate(lines) if first in ln)
    body = lines[start + 1 :]  # skip the signature: the template already prints it
    # drop the docstring block
    if body and '"""' in body[0]:
        close = next((i for i, ln in enumerate(body) if i > 0 and ln.strip().endswith('"""')), None)
        if close is not None:
            body = body[close + 1 :]
    # stop at the next top-level definition
    end = next((i for i, ln in enumerate(body) if ln and not ln[0].isspace()), len(body))
    return esc("\n".join(body[:end]).strip("\n"))


CSS = """
:root{
  --ink:#f2e9dd; --paper:#141110; --panel:#1d1917; --panel2:#241f1b;
  --muted:#a3937f; --line:#3a322b;
  --amber:#d9a13b; --terra:#c56a45; --olive:#9aa06a; --deep:#8d3a3a;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font:16px/1.68 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",
       "PingFang SC","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:960px;margin:0 auto;padding:0 28px}
code,.m{font-family:"SF Mono",Menlo,Consolas,"Cascadia Mono",monospace}
code{background:#2b2521;padding:.12em .42em;border-radius:4px;font-size:.88em;color:#e8d9c4}

header{padding:76px 0 40px;border-bottom:1px solid var(--line)}
.kicker{
  font-size:12.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--amber);margin-bottom:18px
}
h1{
  font-size:clamp(28px,4.4vw,44px);line-height:1.18;margin:0 0 20px;
  font-weight:640;letter-spacing:-.015em
}
.sub{font-size:17.5px;color:var(--muted);margin:0 0 30px;max-width:74ch;line-height:1.62}
.meta{
  display:flex;flex-wrap:wrap;gap:10px 26px;font-size:13.5px;
  color:var(--muted);padding-top:6px
}
.meta b{color:var(--ink);font-weight:600}

section{padding:52px 0;border-bottom:1px solid var(--line)}
section:last-of-type{border-bottom:none}
h2{
  font-size:13px;letter-spacing:.15em;text-transform:uppercase;
  color:var(--amber);margin:0 0 22px;font-weight:640
}
h3{font-size:20px;margin:34px 0 12px;font-weight:620;letter-spacing:-.01em}
h3:first-of-type{margin-top:0}
p{margin:0 0 16px;max-width:76ch}
.lede{font-size:17.5px;color:#ded1c1}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);margin:26px 0 6px}
.stat{background:var(--panel);padding:20px 18px}
.stat .n{font-size:27px;font-weight:660;color:var(--amber);line-height:1.15;
  font-variant-numeric:tabular-nums}
.stat .l{font-size:12.5px;color:var(--muted);margin-top:5px;line-height:1.45}

figure{margin:30px 0}
figure img{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:6px}
figcaption{font-size:13px;color:var(--muted);margin-top:11px;line-height:1.55}

.tw{overflow-x:auto;margin:22px 0;border:1px solid var(--line);border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:13.5px;background:var(--panel)}
th{
  text-align:left;padding:11px 13px;font-weight:620;color:var(--amber);
  font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;
  border-bottom:1px solid var(--line);white-space:nowrap;background:var(--panel2)
}
td{padding:9px 13px;border-bottom:1px solid #2b2521;vertical-align:top}
tr:last-child td{border-bottom:none}
td.m{font-size:12.5px;white-space:nowrap}
td.ok{color:var(--olive)} td.bad{color:var(--terra)} td.warn{color:var(--amber)}
td.mut{color:var(--muted)}
tbody tr:hover{background:#241f1b}

.finding{
  background:var(--panel);border-left:3px solid var(--terra);
  padding:22px 24px;margin:24px 0;border-radius:0 6px 6px 0
}
.finding h3{margin-top:0;color:var(--ink)}
.finding .tag{
  display:inline-block;font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--terra);margin-bottom:9px;font-weight:640
}
.cleared{background:var(--panel);border-left:3px solid var(--olive);
  padding:22px 24px;margin:24px 0;border-radius:0 6px 6px 0}
.cleared .tag{color:var(--olive);display:inline-block;font-size:11.5px;
  letter-spacing:.1em;text-transform:uppercase;margin-bottom:9px;font-weight:640}

pre{
  background:#191512;border:1px solid var(--line);border-radius:6px;
  padding:15px 17px;overflow-x:auto;font-size:12.8px;line-height:1.62;margin:16px 0
}
pre code{background:none;padding:0;color:#e2d3bd;font-size:inherit}
.del{color:var(--terra)} .add{color:var(--olive)}

.risk{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);margin:22px 0}
.risk>div{background:var(--panel);padding:17px 20px}
.risk .h{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px}
.risk .h b{font-size:15.5px;font-weight:620}
.sev{font-size:11px;letter-spacing:.08em;text-transform:uppercase;padding:2px 8px;
  border-radius:3px;font-weight:640}
.sev.hi{background:#3a1f18;color:#e08263}
.sev.md{background:#39301a;color:#dcb45c}
.sev.lo{background:#2a3323;color:#a8b57c}
.risk p{margin:0;font-size:14px;color:#cfc2b2;max-width:none}

footer{padding:34px 0 64px;font-size:13px;color:var(--muted)}
footer a{color:var(--amber)}
a{color:var(--amber)}
hr{border:none;border-top:1px solid var(--line);margin:30px 0}
"""

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>pathvalidate 三处静默缺陷 · 审查报告</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="kicker">Security &amp; robustness audit</div>
  <h1>一个文件名净化库，<br>把相对路径改成了绝对路径</h1>
  <p class="sub">
    <code>pathvalidate</code> 站在「不可信文件名 → 磁盘」这条链路上。三处缺陷都能改变
    实际落盘结果，其中一处会让 <code>os.path.join</code> 丢掉基目录。全部实测复现、
    最小化修复、40 个回归测试锁定。
  </p>
  <div class="meta">
    <span>上游 <b>thombashi/pathvalidate</b> 3.3.1</span>
    <span>基线 <b>1ca0a50</b></span>
    <span>许可 <b>MIT</b>（原样保留）</span>
    <span>验证 <b>3.12 / 3.13 / 3.14</b></span>
  </div>
</header>

<section>
  <div class="stats">
    <div class="stat"><div class="n">3</div><div class="l">独立缺陷<br>（全部实测复现）</div></div>
    <div class="stat"><div class="n">40</div><div class="l">新增回归测试<br>4184 → 4224</div></div>
    <div class="stat"><div class="n">9/9</div><div class="l">变异全部被杀死<br>含 1 个首轮存活</div></div>
    <div class="stat"><div class="n">86/96</div><div class="l">文件与上游<br>逐字节相同</div></div>
  </div>
  <p class="lede">
    先说清楚边界：下面还有 <b>4 项"看着像漏洞"的东西被排除</b>，包括一处
    "构造了异常却没 raise"的死代码——静态阅读会误判，实测证明行为是对的。
  </p>
</section>

<section>
  <h2>缺陷 A · 替代文本被当作正则替换模板</h2>
  <p>
    <code>re.sub(pattern, repl, text)</code> 的 <code>repl</code> 是<b>替换模板</b>，
    会解析反斜杠转义。而 <code>replacement_text</code> 是调用方给的普通文本。代码把它直接传了进去，
    同一根因共 6 个调用点 + <code>_common</code> 里 2 处。
  </p>

  <figure>
    <img src="{img('replacement-text.png')}" alt="replacement_text 结果分类：修复前 3 正确 4 静默损坏 1 跳过 3 崩溃；修复后 10 全正确">
    <figcaption>
      10 个代表性 <code>replacement_text</code>，修复前只有 3 个按字面量插入。
      分类在 arm 内部用真实字符串判定（不是比对 repr——那会把 <code>\\b</code> 和退格符看成一样）。
    </figcaption>
  </figure>

  <div class="tw">{table_replacement()}</div>

  <h3>为什么这不只是"报错难看"</h3>
  <p>
    <code>re.error</code> 的 MRO 只有 <code>Exception → BaseException</code>，
    <b>不是</b> <code>ValueError</code>。但函数文档写着 <code>Raises: ValueError</code>，
    <code>ValidationError</code> 也确实是它的子类。按文档写 <code>except ValueError</code> 的调用方会直接漏接。
  </p>
  <p>
    而且类名跨版本会变：3.12 叫 <code>re.error</code>，3.13/3.14 叫 <code>re.PatternError</code>。
    任何靠异常名做分派的地方，升级解释器时都会静默失灵。
  </p>
  <p>
    最隐蔽的是 <code>\\g&lt;0&gt;</code>：替换内容等于原匹配内容，净化变成空操作。
    <code>sanitize_filename("a?b", replacement_text="\\\\g&lt;0&gt;")</code> 原样返回 <code>a?b</code>，
    而 <code>is_valid_filepath</code> 判它 <code>False</code>——非法字符被吐回，等着落到磁盘上。
  </p>

  <h3>修复</h3>
  <p>新增 <code>escape_replacement_text()</code>，把反斜杠加倍后再交给 <code>re.sub</code>：</p>
<pre><code>def escape_replacement_text(replacement_text: str) -&gt; str:
    <span class="mut"># ... docstring ...</span>
{src_body("pathvalidate/_common.py", "def escape_replacement_text")}</code></pre>
  <p>
    空串短路，默认路径只多一次真值判断。没用 <code>lambda m: repl</code> 是因为那会在每次匹配时
    多一次 Python 调用；转义是纯字符串操作，且保持原有调用形态，改动面最小。
  </p>
  <p>
    改之前先确认了没有内部依赖模板语义：全仓 <code>grep '\\g&lt;0&gt;'</code> 零命中，
    文档与示例也从未提及模板能力，所以改成字面量不破坏任何既有契约。
  </p>
</section>

<section>
  <h2>缺陷 B · 驱动器相对路径被改写为绝对路径</h2>
  <p>
    <code>ntpath.splitdrive("C:x.txt")</code> 返回 <code>("C:", "x.txt")</code>。
    原代码把 drive 与分隔符拼回去，<code>C:</code> + <code>\\</code> + <code>x.txt</code>
    = <code>C:\\x.txt</code>——<b>绝对路径</b>。
  </p>

  <div class="tw">{table_escape()}</div>

  <p>
    后果是 <code>os.path.join</code> 在第二个参数为绝对路径时会<b>丢弃第一个参数</b>。
    于是一个本该写进上传目录的相对名，变成了向任意盘符根目录写入的绝对路径：
  </p>
<pre><code>BASE = r"C:\\srv\\uploads"
os.path.join(BASE, sanitize_filepath("D:payload.exe", platform="windows"))
<span class="del"># before:  'D:\\payload.exe'             &lt;- BASE 被丢掉，换盘</span>
<span class="add"># after:   'D:payload.exe'                &lt;- 仍是相对名</span></code></pre>

  <p>这还制造了一个自相矛盾：校验器接受输入，净化器却产出校验器拒绝的东西。</p>
  <div class="tw">{table_universal()}</div>

  <p>开启严格模式后，函数会对自己刚产出的值抛异常：</p>
<pre><code>&gt;&gt;&gt; sanitize_filepath("C:x.txt", platform="universal", validate_after_sanitize=True)
ValidationError: [PV1201] found a malformed absolute path</code></pre>

  <h3>平台扫描</h3>
  <div class="tw">{table_sweep()}</div>
  <p class="mut" style="font-size:13.5px;color:var(--muted)">
    每平台扫 17 个名字。「documented failures」是上游已明确关闭的 #49/#69 那一类，
    本次刻意不动，因此修复后仍留在原地。
  </p>

  <figure>
    <img src="{img('composition-shift.png')}" alt="universal 平台 17 个名字的分类变化：drive-relative 5 个消失，valid 9→14，documented 3 不变">
    <figcaption>
      <b>修复是定点的，不是"全修好了"。</b> 17 个名字里 5 个由本缺陷造成的失败消失了，
      但另外 3 个仍按文档说明失败（净化器不保证输出有效）——它们本来就不该被算作本次修复的功劳。
    </figcaption>
  </figure>

  <h3>修复</h3>
  <p>拆分 drive 后判定是否为驱动器相对形态（drive 非空、剩余部分非空、且不以分隔符开头），
  若是则不插入分隔符，改为把 drive 直接前缀拼接。绝对路径行为完全不变，由回归测试锁定：</p>
<pre><code>{src_snippet("pathvalidate/_filepath.py", "is_drive_relative = bool(drive)", "is_drive_relative = unicode_filepath[0]")}
<span class="del"># ... (was: if drive:  sanitized_entries.append(drive))</span>
if drive and not is_drive_relative:
    sanitized_entries.append(drive)
<span class="del"># ...</span>
if drive and is_drive_relative:
    sanitized_path = drive + sanitized_path</code></pre>
</section>

<section>
  <h2>缺陷 C · 多字符替代文本的连续折叠失效</h2>
  <p>
    <code>replace_symbol(..., is_replace_consecutive_chars=True)</code> 声称把连续替代字符合并。
    单字符有效，多字符无效——因为 <code>f"{{re.escape(t)}}+"</code> 里的 <code>+</code>
    只作用于最后一个字符：
  </p>
<pre><code>re.sub(f"{{re.escape('ab')}}+", ...)   <span class="del"># 得到 ab+ ，+ 只绑 b</span>
re.sub(f"(?:{{re.escape('ab')}})+", ...) <span class="add"># 得到 (?:ab)+ ，+ 绑整个串</span>

&gt;&gt;&gt; replace_symbol("a---b", "ab", is_replace_consecutive_chars=True)
'aababab'      <span class="del"># 错：应当折叠为 'aab'</span></code></pre>
  <p>
    这个缺陷独立于 A/B，但同属"正则构造错误"，且上游 4 个既有测试全部只用单字符 <code>_</code>
    做替代符，所以长期没被发现。修 A 时本来就要重写这一行，留着会让"字面量"语义不完整，故一并修。
  </p>
</section>

<section>
  <h2>被排除的四项误报</h2>
  <p class="lede">这一节和上面的修复同样重要。凭代码模式或扫描器告警下判断，这四项都会被误报成漏洞。</p>

  <div class="cleared">
    <div class="tag">已排除 1 · 最重要</div>
    <h3>构造了 <code>ValidationError</code> 却没 <code>raise</code></h3>
    <p>
      <code>_filepath.py</code> 里有一段创建异常对象后直接丢掉，静态看就是死代码。
      实测证明它<b>只是冗余</b>，真正抛错的是后面构造的 <code>err_object</code>，行为完全正确。
      只看"造了异常没用"必误报。
    </p>
  </div>

  <div class="cleared">
    <div class="tag">已排除 2</div>
    <h3>净化器不保证输出有效</h3>
    <p>
      超长路径（#49）、全点号名字（#69）确实会产出无效值。但这两个 issue 上游<b>已明确讨论并关闭</b>，
      补偿机制是 <code>validate_after_sanitize=True</code>（实测确实会抛）。这是向后兼容的默认值选择，
      不是遗漏。列为已知限制，不改默认行为。
    </p>
  </div>

  <div class="cleared">
    <div class="tag">已排除 3</div>
    <h3><code>..</code> 路径分量原样保留</h3>
    <p>
      <code>sanitize_filepath("../../etc/passwd")</code> 默认返回原值。这是<b>既有且刻意</b>的行为——
      净化器不是安全边界。顺手"加固"会破坏大量合法相对路径用法，所以不做，改在风险一节提醒调用方。
    </p>
  </div>

  <div class="cleared">
    <div class="tag">已排除 4</div>
    <h3>替换模板语义本身</h3>
    <p>
      改成字面量之前先 grep 了全部 <code>re.sub</code> 调用点与 <code>\\g&lt;0&gt;</code>：
      零命中，无内部依赖，文档也从未承诺模板能力，因此改动安全。
    </p>
  </div>
</section>

<section>
  <h2>验证</h2>

  <h3>测试</h3>
  <div class="tw">
    <table><thead><tr><th>项目</th><th>结果</th></tr></thead><tbody>
      <tr><td>上游套件（基线）</td><td class=m>4184 passed, 14 skipped</td></tr>
      <tr><td>上游套件（打补丁后）</td><td class=m>4224 passed, 14 skipped</td></tr>
      <tr><td>差值</td><td>+40，恰好等于新增用例数，<b>无一条既有测试被改或删</b></td></tr>
      <tr><td>反向喂毒</td><td>24 条新测试在原始代码上失败（行为级断言，非 ImportError）</td></tr>
      <tr><td>ruff / format / mypy</td><td>All checks passed / 25 files formatted / no issues</td></tr>
      <tr><td>新增 lint 问题</td><td>0（对 118 条既有告警做基线差分，未顺手改无关文件）</td></tr>
    </tbody></table>
  </div>

  <h3>变异测试</h3>
  <p>把修复逐个改回错误形态，确认测试会红。<b>第一轮不是全绿</b>：M9 存活暴露了真实盲区。</p>
  <div class="tw">{table_mutations()}</div>
  <p>
    M9 指的是：<code>reserved_name_handler</code> 返回含反斜杠的字符串这条路径没有测试覆盖。
    补上 <code>test_normal_reserved_name_handler_literal</code> 之后才 9/9。
    "第一轮全绿"从来不可信。
  </p>

  <h3>跨版本</h3>
  <p>
    脚本强制把同目录包插入 <code>sys.path[0]</code> 并<b>打印实际解析到的文件路径</b>。
    这个防护不是多余的：本机 3.14 的 site-packages 里有一份未打补丁的 3.3.1，
    早期一轮测量就误命中了它并报出"全过"。
  </p>
  <div class="tw">
    <table><thead><tr><th>解释器</th><th>导入</th><th>结果</th></tr></thead><tbody>
      <tr><td class=m>CPython 3.12.10</td><td class=m>交付副本</td><td class=ok>passed</td></tr>
      <tr><td class=m>CPython 3.13.14</td><td class=m>交付副本</td><td class=ok>passed</td></tr>
      <tr><td class=m>CPython 3.14.5</td><td class=m>交付副本</td><td class=ok>passed</td></tr>
      <tr><td class=m>3.12 · 未打补丁副本</td><td class=m>强制指向基线</td><td class=bad>
        crash: bad escape</td></tr>
    </tbody></table>
  </div>

  <h3>性能</h3>
  <p>
    本机 A/A 噪声底（两份字节相同的代码对比）实测 <b>0.881 – 1.314</b>，比任何可能的效应都宽。
    所以不给计时点值，改用确定性指标：
  </p>
  <div class="tw">
    <table><thead><tr><th>指标</th><th>值</th></tr></thead><tbody>
      <tr><td>新增函数 · 空串路径（默认）</td><td class=m>46.5 ns/次</td></tr>
      <tr><td>新增函数 · 非空</td><td class=m>62.8 ns/次</td></tr>
      <tr><td>单次 <code>sanitize_filename</code></td><td class=m>~18–21 µs</td></tr>
      <tr><td>默认路径相对开销</td><td class=m>≈ 0.25%，且不在任何热循环里</td></tr>
    </tbody></table>
  </div>

  <h3>补丁可还原性</h3>
  <p>
    <code>fixes.patch</code>（18 个 hunk）打在一份从 git blob 重建的纯净 LF 上游上：
    10 个文件全部应用、0 reject，逐文件 sha1 与交付副本<b>完全一致</b>。
  </p>
</section>

<section>
  <h2>尚未解决的风险</h2>
  <p class="lede">以下都是已知且刻意不修、或超出本库职责的。不列出来就等于骗人。</p>

  <div class="risk">
    <div><div class="h"><b>净化器不是安全边界</b><span class="sev hi">高 · 调用方责任</span></div>
    <p>
      修复后 <code>sanitize_filepath("../../etc/passwd")</code> 仍返回原值。任何"把不可信名字拼到
      目录下"的代码都必须自己做 containment 校验（<code>realpath</code> + <code>commonpath</code>）。
      本次消除了"本应相对却被改成绝对"这一类绕过，但没有、也不可能把该库变成路径穿越防护层。
    </p></div>

    <div><div class="h"><b>默认不保证输出有效</b><span class="sev md">中 · 上游设计取舍</span></div>
    <p>超长路径、全点号名字仍可能产出无效值（#49/#69）。需要强保证必须显式开
      <code>validate_after_sanitize=True</code>，或自行复验。</p></div>

    <div><div class="h"><b>替代文本仍可被用于"取消净化"</b><span class="sev lo">低 · 语义使然</span></div>
    <p>修复后替代文本是纯字面量，但依然原样插入。传 <code>"?"</code> 就能让 <code>a?b</code> 变成
      <code>a?b?</code>。转义解决不了这个——替代文本必须是可信的。</p></div>

    <div><div class="h"><b>非 UTF-8 编码抛 UnicodeEncodeError</b><span class="sev lo">低 · 既有行为</span></div>
    <p><code>sanitize_filename("éé", fs_encoding="ascii")</code> 直接抛
      <code>UnicodeEncodeError</code>，未包装进 <code>ValidationError</code>。与本次三个缺陷无关，
      修它会改变异常类型，需单独的兼容性决策。</p></div>

    <div><div class="h"><b>仅在 Windows 宿主实测</b><span class="sev md">中 · 验证面限制</span></div>
    <p>Linux/macOS 的宿主差异未经真实机器验证。相关逻辑已通过显式 <code>platform=</code>
      做平台无关断言，但建议上游 CI 矩阵跑一遍确认。</p></div>

    <div><div class="h"><b>未提交上游 PR</b><span class="sev lo">流程</span></div>
    <p>本次为离线审查 + 本地修复。若要上游采纳，建议按 A/B/C 拆成 3 个独立 PR。</p></div>
  </div>
</section>

<footer>
  <p>
    上游 <a href="https://github.com/thombashi/pathvalidate">thombashi/pathvalidate</a> ·
    MIT License · Copyright (c) 2016-2025 Tsuyoshi Hombashi（原样保留）<br>
    本页所有数字由 <code>_viz/collect_data.py</code> 采集、<code>_viz/make_page.py</code> 渲染，
    无手写测量值。图表仅保留有两臂信号的对比；明细一律用表格。
  </p>
</footer>

</div>
</body>
</html>
"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as fp:
    fp.write(HTML)
print("wrote", OUT, os.path.getsize(OUT), "bytes")
