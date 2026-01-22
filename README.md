# b站up粉丝数定时推送插件

插件可实现按指定分钟间隔推送b站up的粉丝数。

插件依赖 `bilibili-api-python` 库，在AstrBot插件市场安装插件后，通常情况下，AstrBot会自动解决依赖问题，若未自动安装可自行在AstrBot Web控制台右上角手动安装。

### 使用方法

---

- 命令：

采用指令组 `/bwatch` ，指令组内所有指令均为**管理员指令**。

此指令组的子指令：

​	`/bwatch add` 在当前会话中添加要监控的UP，指令规则为 `/bwatch add [uid] [time] [ifequal]` 

​	uid (str): UP主的UID（发送时无需带 `UID` 前缀，纯数字即可）

​	time (str): 检查间隔时间（分钟）

​	ifequal (str): 相等时是否推送（仅支持 `true/false`）



​	`/bwatch del` 删除当前会话中正在监控的UP，指令规则为 `/bwatch del [uid]` 

​	uid (str): UP主的UID（发送时无需带 `UID` 前缀，纯数字即可）



​	`/bwatch list` 列出当前会话中所有正在监控的UP项。

​	`/bwatch test` 获取并发送一次在当前会话中所有已添加的监控项结果以测试效果。

- 配置

  desc：要监控的B站up列表

  每个监控项都是一个字典(dict)，所有监控项使用列表(list)存储。

  示例：

  ```json
  {
    "uplist": [
      {
        "uid": 8047632,
        "time": 60,
        "ifequal": "true",
        "umo": "aiocqhttp:GroupMessage:1145141919"
      },
      {
        "uid": 8047632,
        "time": 120,
        "ifequal": "false",
        "umo": "aiocqhttp:FriendMessage:1919810114"
      }
    ]
  }
  ```



# 支持

[AstrBot 帮助文档](https://astrbot.app)
