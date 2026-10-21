# 给队友：加入 Team23 项目仓库的完整步骤

> 写给 Morty（王志远）、Spring（王春希）、Jensen（龚俊诚）
> 项目：MeítǐShāngchéng 员工管理系统（Team 23 · ZZULI & Fontys）
> 仓库地址：https://github.com/JJC-Dylan/team23-ems

---

## 你要做的总共 5 步

1. 注册 GitHub 账号（约 5 分钟）
2. 把用户名发给 Dylan
3. 接受邀请
4. 把代码下载到自己电脑
5. 运行起来看效果

---

# 第 1 步：注册 GitHub 账号

**网址**：https://github.com

1. 点右上角 **Sign up**
2. 填：邮箱、密码、用户名（用户名建议用英文，比如 `morty-wang`）
3. 完成邮箱验证（去邮箱点确认链接）
4. 记下你的**用户名**（就是个人主页地址里那一串，例如 `https://github.com/morty-wang` 中的 `morty-wang`）

> ⚠️ **注意网络问题**：国内直接打开 GitHub 可能很慢或打不开。
> 如果打不开，请开代理（Clash 等），把 `github.com` 走代理规则。
> 这一步几乎人人都会遇到，不是你电脑坏了。

---

# 第 2 步：把用户名发给 Dylan

注册好后，**把用户名（不是密码！）发给 Dylan**，例如：

```
我的 GitHub 用户名是：morty-wang
```

> 🔒 **只发用户名，绝对不要发密码或 Token。**

Dylan 收到后会在仓库里把你加为协作者。

---

# 第 3 步：接受邀请

Dylan 加你之后，会有两种情况：

**情况 A：收到邮件**
去邮箱找一封来自 GitHub 的邀请邮件 → 点 **View invitation** → 点 **Accept invitation**

**情况 B：没收到邮件**
直接打开这个网址（登录状态下）：

```
https://github.com/JJC-Dylan/team23-ems/invitations
```

看到邀请后点 **Accept**。

**成功标志**：打开 https://github.com/JJC-Dylan/team23-ems 能正常看到代码。

---

# 第 4 步：把代码下载到自己电脑

## 方式 A：直接下载 ZIP（最简单，推荐先用这个）

1. 打开 https://github.com/JJC-Dylan/team23-ems
2. 点绿色的 **Code** 按钮
3. 点 **Download ZIP**
4. 解压到你喜欢的目录，例如 `D:\team23-website`

> 这个方式**不需要装 Git**，也不会有网络代理的麻烦，适合先跑起来看效果。

## 方式 B：用 git clone（要给项目提交代码时必须用）

**前提：电脑上装了 Git**（https://git-scm.com/download/win）

然后在命令行里：

```
git clone https://github.com/JJC-Dylan/team23-ems.git
```

⚠️ **国内大概率需要给 Git 配代理**，否则会报 `Connection was reset`。
如果你的代理端口是 7890，执行这两条：

```
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

（代理端口不一定都是 7890，看你自己代理软件的设置。Clash 一般是 7890。）

> 关掉代理后如果 git 连不上，用这两条取消代理：
> ```
> git config --global --unset http.proxy
> git config --global --unset https.proxy
> ```

---

# 第 5 步：运行项目

## 需要的东西

- **Python 3.10 或更高版本**（https://www.python.org/downloads/）
  安装时**务必勾选 "Add Python to PATH"**
- **PyCharm**（你已经有的话跳过）

## 用 PyCharm 运行（推荐）

1. PyCharm → **File → Open** → 选择解压出来的 `team23-website` 文件夹
2. 如果提示配置解释器，选你电脑上的 **Python 3.10+**
3. 左侧文件树里找到最外层的 **`app.py`** → **右键 → Run 'app'**
4. 底部出现一段带横线的文字，浏览器自动打开登录页
5. 用 `hr` / `hr123` 登录

**不需要 pip install 任何东西**，项目只用 Python 自带的功能。

## 用命令行运行（PyCharm 装不上时）

打开命令提示符，cd 到项目目录，执行：

```
python app.py
```

然后浏览器打开 http://127.0.0.1:8000

---

# 演示账号

| 角色 | 用户名 | 密码 | 能做什么 |
|---|---|---|---|
| HR | `hr` | `hr123` | 增删改员工 |
| 主管 | `supervisor` | `super123` | 排班 |
| 普通员工 | `employee` | `emp123` | 只看自己的班次 |

---

# 常见问题

**Q: 打开 GitHub 一直转圈 / 报错**
A: 国内访问 GitHub 不稳定，开代理。如果实在不行，告诉 Dylan，我们可能改用 Gitee。

**Q: 点邀请链接提示 404**
A: 说明你的用户名还没被加上去，或者加的时候名字拼错了。把准确用户名重发给 Dylan。

**Q: 运行 `python app.py` 报 "不是内部或外部命令"**
A: Python 没装或没加到 PATH。重新装 Python，安装时勾选 "Add Python to PATH"。

**Q: 运行报 `SyntaxError`**
A: 你的 Python 版本太旧。这个项目要求 **3.10 以上**，用 `python --version` 查看版本。

**Q: 页面打不开**
A: 检查命令行窗口是否还在运行（关掉窗口服务器就停了）；端口 8000 是否被占用，可以换端口：`python app.py --port 8100`

**Q: 改了代码怎么提交回仓库？**
A: 需要先被加为协作者，然后：
```
git add .
git commit -m "说明你改了什么"
git push
```

---

# 各人负责的模块（按项目计划分工）

| 成员 | 负责模块 | 主要文件 |
|---|---|---|
| Dylan | 员工信息模块 | `app/views.py`、`app/repositories.py` |
| Spring | 排班模块 | `app/views.py` 中的 shift 相关函数 |
| Morty | 数据库后端 | `app/database.py`、`app/repositories.py` |
| Jensen | 前端界面 | `templates/`、`static/` |

---

# 有问题怎么办

先在群里问，别自己乱改。

**重要**：不要提交 `.venv` 文件夹和 `data` 文件夹（已经在 `.gitignore` 里排除了，正常不会提交）。
