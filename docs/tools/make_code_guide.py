"""Generate the code-explanation handbook (DOCX) for Team 23.

Every snippet in the document is read from the real source files at generation
time, so the document can never drift from the code.

Run with the bundled Python:
    python docs/tools/make_code_guide.py
"""

from __future__ import annotations

import os
import re

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Cm, RGBColor

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DELIVERABLES_DIR = r"C:\Users\金俊臣\Desktop\唧唧C的文件\2026下期-软件工程项目规划"
OUTPUT_NAME = "Code Guide-Team 23.docx"

BLUE = RGBColor(0x1F, 0x4E, 0x79)
GREY = RGBColor(0x55, 0x55, 0x55)
CODE_COLOUR = RGBColor(0x1A, 0x1A, 0x1A)


def read_source(relative_path: str) -> list[str]:
    path = os.path.join(PROJECT_ROOT, relative_path)
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


def extract(relative_path: str, start_pattern: str, max_lines: int = 40,
            end_pattern: str | None = None) -> str:
    """Return source lines from the first line matching ``start_pattern``."""
    lines = read_source(relative_path)
    pattern = re.compile(start_pattern)
    for index, line in enumerate(lines):
        if pattern.search(line):
            collected = [line]
            for offset in range(1, max_lines):
                if index + offset >= len(lines):
                    break
                candidate = lines[index + offset]
                if end_pattern and re.search(end_pattern, candidate):
                    break
                collected.append(candidate)
            return "\n".join(collected).rstrip()
    return f"(pattern not found: {start_pattern})"


def _shade(paragraph, fill: str = "F4F6F8") -> None:
    properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _preserve(element) -> None:
    for text_node in element.iter(qn("w:t")):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def code_block(document, code: str, caption: str | None = None) -> None:
    for line in code.split("\n"):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.left_indent = Cm(0.4)
        paragraph.paragraph_format.line_spacing = 1.0
        run = paragraph.add_run(line if line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(7.5)
        run.font.color.rgb = CODE_COLOUR
        _shade(paragraph)
        _preserve(paragraph._p)
    if caption:
        note = document.add_paragraph()
        note.paragraph_format.space_before = Pt(2)
        run = note.add_run(caption)
        run.italic = True
        run.font.size = Pt(8.5)
        run.font.color.rgb = GREY


def body(document, text: str) -> None:
    paragraph = document.add_paragraph(text)
    paragraph.paragraph_format.space_after = Pt(4)


def bullets(document, items: list[str]) -> None:
    for item in items:
        document.add_paragraph(item, style="List Bullet")


def table(document, headers, rows, widths):
    table_obj = document.add_table(rows=1, cols=len(headers))
    table_obj.style = "Table Grid"
    table_obj.autofit = False
    for index, header in enumerate(headers):
        cell = table_obj.rows[0].cells[index]
        cell.text = ""
        run = cell.paragraphs[0].add_run(header)
        run.bold = True
        run.font.size = Pt(9)
    for row in rows:
        cells = table_obj.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = ""
            cells[index].paragraphs[0].add_run(str(value)).font.size = Pt(8.5)
    for index, width in enumerate(widths):
        table_obj.columns[index].width = Cm(width)
        for row in table_obj.rows:
            row.cells[index].width = Cm(width)
    document.add_paragraph()


def build() -> Document:
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    title = document.add_heading("Code Guide", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = document.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("Employee Management System for MeítǐShāngchéng · Team 23")
    run.bold = True
    run.font.size = Pt(11)
    note = document.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note_run = note.add_run("本文档中的代码片段均由脚本从真实源文件读取，不是手抄的。")
    note_run.italic = True
    note_run.font.size = Pt(9)
    note_run.font.color.rgb = GREY

    # ================================================================ 1
    document.add_heading("1 项目概况", level=1)
    table(document,
          ["项目", "内容"],
          [
              ["系统名称", "MeítǐShāngchéng 员工管理系统"],
              ["技术栈", "Python 3.10+ 标准库（零第三方依赖）+ SQLite"],
              ["代码规模", "9 个模块约 2400 行 Python；11 个 HTML 模板；1 个 CSS；1 个 JS"],
              ["测试", "97 个自动化单元/集成测试，全部通过"],
              ["运行方式", "python app.py → 浏览器访问 http://127.0.0.1:8000"],
          ],
          [4.0, 13.0])

    # ================================================================ 2
    document.add_heading("2 整体架构", level=1)
    body(document, "代码分为五层，每层只做一件事。请求从上往下走，数据从下往上返回。")
    code_block(document, """浏览器
   ↓ HTTP 请求
app/server.py          多线程 HTTP 服务器（WSGI）
   ↓
app/app.py             路由匹配 → 权限校验 → CSRF 校验 → 错误处理
   ↓
app/views.py           每个页面的业务逻辑
   ↓
app/repositories.py    全部 SQL 语句
   ↓
app/database.py        SQLite 文件 data/employee_management.db""",
               "图 1：一次请求经过的五层。")

    body(document, "这样分层的好处：改页面逻辑只动 views.py，改数据库查询只动 repositories.py，"
                   "两者互不干扰，也方便分别写测试。")

    # ================================================================ 3
    document.add_heading("3 启动流程：app.py", level=1)
    body(document, "最外层的 app.py 是入口。它做三件事：读参数、建数据库、启动服务器。")
    code_block(document, extract("app.py", r"^def main\(", max_lines=22),
               "app.py：main() 的前半段。")

    body(document, "这里的关键点：")
    bullets(document, [
        "PROJECT_ROOT 加进 sys.path —— 这样无论在哪个目录运行，都能 import 到 app 包。",
        "Application(...) 的构造函数里会建表、并在数据库为空时插入 5 个演示员工。",
        "serve_forever(...) 是阻塞调用，Ctrl+C 才退出。",
    ])

    # ================================================================ 4
    document.add_heading("4 Web 核心：app/app.py", level=1)
    body(document, "这是整个系统的骨架，420 行左右，负责五件事：收请求、找路由、查权限、"
                   "防伪造、处理异常。")

    document.add_heading("4.1 路由注册：一条路由声明自己的权限", level=2)
    code_block(document, extract("app/app.py", r"    def route\(", max_lines=14),
               "route() 装饰器：把 URL 模式、允许的角色和处理函数绑在一起。")
    body(document, "以 /employees/new 为例：")
    code_block(document,
               'app.route("/employees/new", methods=("GET", "POST"), roles=HR_ONLY)(employee_create)',
               "roles=HR_ONLY 意味着只有 HR 能进，其他人即使知道地址也会被拦。")

    document.add_heading("4.2 权限校验：_authorize()", level=2)
    code_block(document, extract("app/app.py", r"    def _authorize\(", max_lines=16),
               "每条路由处理前都会经过这里。")
    body(document, "这段是整个权限设计的核心。要点：")
    bullets(document, [
        "roles 为空元组 → 公开页面（比如登录页），直接放行。",
        "没有会话 → 重定向到登录页，并记住原本要去的地址。",
        "角色不匹配 → 抛 HttpError(403)，由统一的错误处理渲染成友好页面。",
        "前端隐藏按钮只是辅助，真正的拦截在这里 —— 这是 NFR02 的要求。",
    ])

    document.add_heading("4.3 防 CSRF：_check_csrf()", level=2)
    code_block(document, extract("app/app.py", r"    def _check_csrf\(", max_lines=14),
               "只对会改变数据的请求（POST/PUT/DELETE）生效。")
    body(document, "CSRF 的原理：别的网站诱导浏览器带着你的 Cookie 往我们这里发请求。"
                   "防范方法：每个表单带一个随会话生成的随机令牌，服务端比对，不一致就拒绝。")

    # ================================================================ 5
    document.add_heading("5 业务层：app/views.py", level=1)
    body(document, "每个页面一个函数。以「新增员工」为例，这个函数同时演示了校验、保存、重定向三件事。")
    code_block(document, extract("app/views.py", r"^def employee_create\(", max_lines=38),
               "views.py：employee_create()。")

    body(document, "逐段解释：")
    table(document,
          ["代码段", "作用"],
          [
              ["if request.method == \"POST\":", "区分「打开表单」和「提交表单」两种请求"],
              ["form = {...}", "把表单字段收集成一个字典"],
              ["try: validate_employee(form)", "调校验函数；不合法会抛 ValidationError"],
              ["except ValidationError", "重新渲染表单，带上错误信息和用户已填的内容（URS 用例 1A）"],
              ["repo.create_employee(...)", "校验通过才写数据库"],
              ["request.flash(...)", "记一条成功提示，跳转后显示"],
              ["response.redirect(...)", "303 重定向到新员工详情页（防止刷新重复提交）"],
          ],
          [6.5, 10.5])

    document.add_heading("5.1 周排班的写入与三种角色视图", level=2)
    body(document, "排班是本项目最「业务」的一段代码：一条记录 = 员工 + 日期 + 班次，"
                   "所以同一天可以排早班和晚班两条；写入用 ON CONFLICT 保证不重复。")
    code_block(document,
               extract("app/views.py", r"^def employee_assign_shift\(", max_lines=80,
                       end_pattern=r"^def "),
               "views.py：employee_assign_shift()，校验日期和班次后才写入。")
    body(document, "页面按角色渲染不同的形状，但都用同一个数据源：")
    table(document,
          ["角色", "视图", "代码"],
          [
              ["普通员工", "个人周课表：行=三个班次，列=周一到周日，格子打勾",
               "my_shifts() → employee_week_shifts()"],
              ["Supervisor", "按天分组：每天列出三个班次分别有谁",
               "store_shifts() → day_roster()"],
              ["HR", "按员工分组：每个人一周的班次，可筛选",
               "store_shifts() → employee_roster()"],
          ],
          [3.2, 8.3, 5.5])
    body(document, "周参数统一由 `_week_from_request()` 处理：`?week=` 传该周任意一天即可，"
                   "内部换算成周一；传入不可读的值就回退到本周，不会让页面报错。")

    # ================================================================ 6
    document.add_heading("6 数据层", level=1)

    document.add_heading("6.1 表结构：app/database.py", level=2)
    code_block(document, extract("app/database.py", r"CREATE TABLE IF NOT EXISTS shifts", max_lines=14),
               "database.py：shifts 表的定义（按日期的周排班）。")
    body(document, "三个关键设计：")
    bullets(document, [
        "employee_id ... ON DELETE CASCADE —— 删员工时该员工的所有排班自动删除，不会留下孤儿数据（URS 用例 5 第 3 步）。",
        "shift_name CHECK (... IN ('Morning','Afternoon','Evening')) —— 数据库层只允许三种班次。",
        "UNIQUE INDEX (employee_id, work_date, shift_name) —— 一人一天一个班次一条；同一天可以排多个班次（老师确认的需求）。",
    ])
    body(document, "班次时间集中在 `SHIFT_TIMES`：早班 08:00–12:00、中班 14:00–18:00、晚班 20:00–22:00，"
                   "`shift_window()` 负责把它渲染成页面上的文字。都不跨天，所以一条排班只属于一个日期。")

    document.add_heading("6.2 查询：app/repositories.py", level=2)
    body(document, "所有 SQL 都集中在这一个文件，页面函数不直接写 SQL。以搜索为例：")
    code_block(document, extract("app/repositories.py", r"    if query:", max_lines=12),
               "repositories.py：按关键词搜索，同时支持工资区间、班次、排序。")
    body(document, "注意 `:pattern`、`:wage_min` 这些命名占位符 —— 所有用户输入都作为参数传入，"
                   "绝不用字符串拼接。这是防 SQL 注入的标准做法。")

    document.add_heading("6.3 排班写入：upsert", level=2)
    body(document, "同一个员工、同一天、同一个班次再次提交时，不新增一行，而是更新已有那一行：")
    code_block(document,
               """INSERT INTO shifts (employee_id, work_date, shift_name, assigned_at, assigned_by)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(employee_id, work_date, shift_name) DO UPDATE SET
    assigned_at = excluded.assigned_at,
    assigned_by = excluded.assigned_by""",
               "同样的员工+日期+班次只刷新「谁在什么时间确认的」；换一个班次就是新的一行。")

    document.add_heading("6.4 周排班查询", level=2)
    body(document, "一周用「周一..周日」七个日期表示，一个 `BETWEEN ? AND ?` 就能取出一周的数据，"
                   "员工课表、主管按天视图、HR 按人视图都基于这个周范围。")
    code_block(document, extract("app/repositories.py", r"^def employee_week_shifts\(",
                                 max_lines=40, end_pattern=r"^def "),
               "repositories.py：employee_week_shifts()，返回「日期 → 该日的班次列表」。")
    body(document, "全店视图再用同样的周范围做两次分组：`day_roster()` 按天分组给主管，"
                   "`employee_roster()` 按员工分组给 HR。SQL 只负责取数，分组放在 Python 里，"
                   "所以同一个查询结果能被三种视图复用。")

    # ================================================================ 7
    document.add_heading("7 安全：app/security.py", level=1)
    body(document, "密码绝不明文存储。这里用 PBKDF2-HMAC-SHA256 加盐哈希。")
    code_block(document, extract("app/security.py", r"^def hash_password\(", max_lines=5), "")
    code_block(document, extract("app/security.py", r"^def verify_password\(", max_lines=12), "")
    body(document, "解释要点：")
    bullets(document, [
        "secrets.token_bytes(16) 生成 16 字节随机盐 —— 每个密码的盐都不同，同样的密码哈希也不同。",
        "pbkdf2_hmac 迭代 200000 次 —— 故意变慢，让暴力破解的成本高到不可行。",
        "hmac.compare_digest 是常量时间比较 —— 防止攻击者通过响应时间推测密码。",
        "数据库里存的是 `算法$迭代次数$盐$哈希` 这样一个字符串。",
    ])

    # ================================================================ 8
    document.add_heading("8 输入校验：app/htmlpages.py", level=1)
    code_block(document, extract("app/htmlpages.py", r"    wage_text = ", max_lines=18),
               "htmlpages.py：时薪的校验逻辑。")
    body(document, "校验规则集中在一个函数里，返回值是清洗后的数据，"
                   "错误则抛 ValidationError 并带一个「字段 → 提示」的字典，"
                   "页面就能逐字段显示错误。")

    # ================================================================ 9
    document.add_heading("9 模板引擎：app/templateengine.py", level=1)
    body(document, "因为要求零依赖，不能用 Jinja2，所以自己写了一个约 660 行的小模板引擎。"
                   "它的工作方式：把 HTML 模板编译成 Python 代码，再执行。")
    code_block(document, extract("app/templateengine.py", r"    def _compile\(", max_lines=10),
               "templateengine.py：把模板编译成一个 Python 函数。")
    body(document, "支持这些语法：")
    table(document,
          ["模板语法", "含义"],
          [
              ["{% extends 'base.html' %}", "继承母版，共用导航栏和页脚"],
              ["{% block content %}", "子模板填充的区域"],
              ["{{ variable }}", "输出变量，自动做 HTML 转义（防 XSS）"],
              ["{% for x in items %}", "循环"],
              ["{% if %}", "条件判断"],
          ],
          [6.5, 10.5])
    body(document, "**最重要的特性：默认自动转义。** 任何 {{ }} 输出的内容都会先把 < > & 转成实体，"
                   "所以即使数据里有恶意脚本，也不会被执行。")

    # =============================================================== 10
    document.add_heading("10 前端：templates/ 与 static/", level=1)
    body(document, "11 个 HTML 模板，一个 CSS，一个 JS。设计上的三个要点：")
    bullets(document, [
        "base.html 是母版：导航栏按角色渲染不同链接，普通员工根本看不到管理入口。",
        "班次用颜色区分：早班橙、中班蓝、晚班紫、未排班灰，方便一眼扫全店。",
        "个人周课表用 `.timetable` 网格：行=班次、列=周一到周日、表头带日期、今天高亮，"
        "格子里打勾表示上班；每格还带 `data-date`/`data-shift` 和读屏文字，键盘和屏幕阅读器都能用。",
        "app.js 只有一个功能：删除前的二次确认弹窗。所有样式和脚本都在本地，断网也能用。",
    ])

    # =============================================================== 11
    document.add_heading("11 测试：tests/", level=1)
    table(document,
          ["测试文件", "数量", "测什么"],
          [
              ["test_auth_and_access.py", "20", "登录、登出、登录落点、三种角色的权限矩阵"],
              ["test_employees.py", "34", "员工增删改查、校验、级联删除、持久化、首页分布表"],
              ["test_shifts.py", "58", "周排班（日期、一天多班、翻周）、三种角色视图、旧表迁移、人数统计"],
              ["test_nonfunctional.py", "7", "400+ 数据下的响应时间、10 并发用户"],
              ["test_templateengine.py", "10", "模板引擎的继承、循环、转义"],
              ["test_live_server.py", "8", "真实 HTTP 服务器、静态文件、目录穿越防护"],
          ],
          [6.0, 2.0, 9.0])
    body(document, "运行命令：python -m unittest discover -s tests -t . -v  （当前 137 个测试全部通过）")

    # =============================================================== 12
    document.add_heading("12 高频提问与答法", level=1)
    qa_pairs = [
        ("这段代码为什么这么分层？",
         "为了让职责单一：页面逻辑、SQL、校验各自独立。改一处不影响另一处，也方便分别测试。"),
        ("为什么不用 Django/Flask？",
         "要求零依赖、clone 下来就能跑。自己写 WSGI 层和模板引擎，也让我们能解释每一层。"),
        ("怎么防止用户看到别人的数据？",
         "员工页面用的员工 ID 来自服务端会话，不来自网址参数；且访问管理页面直接返回 403。"),
        ("数据库为什么用 SQLite？",
         "单店内部工具、最多 10 个并发用户。零配置、单文件，备份就是复制文件。"),
        ("怎么保证数据不丢？",
         "全部写进 SQLite 文件，程序重启后还在。这一点有专门的脚本「停服务器→重启」验证过。"),
        ("如果两个人同时改同一个班次会怎样？",
         "同一条（员工+日期+班次）后提交的覆盖先提交的；同一天的不同班次两条都会保留。SQLite 会串行化写入，数据不会损坏。"),
        ("为什么三个角色的排班页面不一样？",
         "老师要求每个角色展现方式不同：员工看自己的周课表（行=班次，列=星期），"
         "主管按天看全店谁在上班，HR 按人看每个人这周上什么班。数据是同一份，只是渲染形状不同。"),
    ]
    for question, answer in qa_pairs:
        head = document.add_paragraph()
        head.paragraph_format.space_before = Pt(8)
        head.paragraph_format.space_after = Pt(1)
        run = head.add_run(f"Q：{question}")
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = BLUE
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.4)
        paragraph.add_run(f"A：{answer}").font.size = Pt(9.5)

    return document


def main() -> None:
    document = build()
    # The project copy is what the repository and the acceptance run use; a
    # read-only or sandboxed deliverables folder must not stop the build.
    targets = [os.path.join(PROJECT_ROOT, "docs", OUTPUT_NAME)]
    if os.path.isdir(DELIVERABLES_DIR):
        targets.insert(0, os.path.join(DELIVERABLES_DIR, OUTPUT_NAME))
    for target in targets:
        try:
            document.save(target)
        except (OSError, PermissionError) as error:
            print(f"skipped: {target}  ({error})")
            continue
        print(f"saved: {target}  ({os.path.getsize(target):,} bytes)")


if __name__ == "__main__":
    main()
