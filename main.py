import asyncio
from datetime import datetime, timedelta

import aiohttp
from bilibili_api import user

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig

# 手动构建不包含消息隔离特征的unified_msg_origin（umo）获取方法
def get_original_umo(event: AstrMessageEvent) -> str:
    return f"{event.get_platform_name()}:{event.message_obj.type.value}:{event.message_obj.session_id}"


@register("astrbot_plugin_upfanswatcher", "laopanmemz", "b站粉丝数定时推送", "1.0.3")
class UPfansWatcher(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        self.session = aiohttp.ClientSession()
        self.runtask = asyncio.create_task(self.task_run())
        logger.info("已启动")

    async def task_run(self):
        """遍历任务并开始执行"""
        logger.info("task_run已启动")
        self.running_tasks = []

        # 按照不同的时间间隔分组任务
        time_groups = {}
        for item in self.config["uplist"]:
            time_interval = item["time"]
            if time_interval not in time_groups:
                time_groups[time_interval] = []
            time_groups[time_interval].append(item)

        # 为每个时间间隔创建一个独立的任务
        for time_interval, items in time_groups.items():
            logger.debug(f"time_interval: {time_interval}, items: {items}")
            task = asyncio.create_task(self._run_periodic_tasks(time_interval, items))
            self.running_tasks.append(task)

        # 等待所有任务完成（实际上这些任务是持续运行的）
        await asyncio.gather(*self.running_tasks, return_exceptions=True)

    async def _run_periodic_tasks(self, interval_minutes, items):
        """根据指定的时间间隔运行周期性任务"""
        logger.debug(
            f"_run_periodic_tasks: interval_minutes:{interval_minutes}, items: {items}"
        )
        while True:
            try:
                # 计算距离下一个整点执行时间的延迟
                now = datetime.now()
                # 计算从今天0点开始，经过了几个interval_minutes的时间段
                total_minutes_since_midnight = now.hour * 60 + now.minute
                next_check_offset = (
                    (total_minutes_since_midnight // interval_minutes) + 1
                ) * interval_minutes
                # 计算下次执行的具体时间
                next_run_hour = next_check_offset // 60
                next_run_minute = next_check_offset % 60
                logger.debug(
                    f"_run_periodic_tasks: next_run_time: {next_run_hour}, next_run_minute: {next_run_minute}"
                )

                # 如果小时超过24，则调整为明天的时间
                if next_run_hour >= 24:
                    next_run_hour -= 24
                    # 这里简单处理，实际应用中可能需要更精确的时间计算
                    next_run_time = datetime(
                        now.year, now.month, now.day, next_run_hour, next_run_minute
                    )
                    if next_run_time <= now:
                        next_run_time += timedelta(days=1)
                else:
                    next_run_time = datetime(
                        now.year, now.month, now.day, next_run_hour, next_run_minute
                    )

                # 如果计算出的时间已经过了今天的范围，调整到明天
                if next_run_time.date() == now.date() and next_run_time <= now:
                    next_run_time = datetime(
                        now.year, now.month, now.day, 0, 0
                    ) + timedelta(minutes=interval_minutes)
                    if next_run_time <= now:
                        # 如果还是小于等于当前时间，则跳转到下一个周期
                        periods_passed = (
                            int(
                                (
                                    now - datetime(now.year, now.month, now.day, 0, 0)
                                ).total_seconds()
                                / 60
                                / interval_minutes
                            )
                            + 1
                        )
                        next_run_time = datetime(
                            now.year, now.month, now.day, 0, 0
                        ) + timedelta(minutes=periods_passed * interval_minutes)

                delay = (next_run_time - now).total_seconds()
                logger.debug(
                    f"_run_periodic_tasks: next_run_time: {next_run_time}, delay: {delay}"
                )
                if delay > 0:
                    await asyncio.sleep(delay)

                # 执行该时间间隔下的所有任务
                for item in items:
                    logger.info(f"开始执行当前间隔下的任务: {item}")
                    await self._execute_single_task(item)

            except Exception as e:
                logger.error(f"执行周期任务时出现错误: {e}")
                # 出错后等待一段时间再继续
                await asyncio.sleep(60)

    async def _execute_single_task(self, item):
        """执行单个任务"""
        logger.debug(f"_execute_single_task: item: {item}")
        uid = item["uid"]
        umo = item["umo"]
        ifequal = item["ifequal"]
        # 检查配置是否仍然存在
        if not any(i["uid"] == uid and i["umo"] == umo for i in self.config["uplist"]):
            return  # 跳过已删除的项目
        result = await self.fans_compare(uid)
        logger.debug(f"_execute_single_task: result: {result}")
        # 判断是否需要发送消息
        should_send = True
        if "未发生变化" in result and ifequal == "false":
            should_send = False

        if should_send:
            message_chain = MessageChain().message(result)
            await self.context.send_message(umo, message_chain)
            logger.info("已发送消息")

    async def get_upfans(self, uid: int):
        """获取UP粉丝数"""
        # 使用Bilibili-API-Python获取UP的粉丝数，暂时没看到要Cookie鉴权，那就直接用官方接口拉取吧~
        u = user.User(uid)
        result = await u.get_relation_info()
        return result["follower"]

    async def get_upname(self, uid: int):
        """获取UP昵称"""
        # 使用官方API需要Cookie，这里采用第三方（Uapi）来获取UP的昵称，免去了鉴权（不知道这个API平台到时候要不要API-KEY）
        try:
            async with self.session.get(
                f"https://uapis.cn/api/v1/social/bilibili/userinfo?uid={uid}"
            ) as resp:
                data = await resp.json()
                await self.put_kv_data(
                    f"{str(uid)}_name", data["name"]
                )  # 将本次成功获取的值持久化存储
                return data["name"]
        except Exception as e:
            logger.error(f"获取UP昵称时出现错误: {e}")
            try:
                async with self.session.get(
                    f"https://api.chyt.top/get_bilibili_info?mid={uid}"
                ) as resp:
                    data = await resp.json()
                    await self.put_kv_data(
                        f"{str(uid)}_name", data["username"]
                    )  # 将本次成功获取的值持久化存储
                    return data["username"]
            except Exception as e:
                logger.error(
                    f"获取UP昵称时再次出现错误，尝试读取上一次获取结果缓存值。以下为错误信息: {e}"
                )
                cache_name = await self.get_kv_data(
                    f"{str(uid)}_name", None
                )  # 尝试读取持久化信息
                if cache_name is not None:  # 若获取到，返回值
                    return cache_name
                else:
                    return "获取UP昵称时出现错误"
                # 实在获取不到了，直接返回错误

    async def fans_compare(self, uid: int):
        """返回UP粉丝数比较结果内容"""
        fans = await self.get_upfans(uid)  # 获取当前最新UP粉丝数
        name = await self.get_upname(uid)  # 获取UP名称
        old_fanscount = await self.get_kv_data(str(uid), None)

        # 首次获取，没有旧数据
        if old_fanscount is None:
            await self.put_kv_data(str(uid), fans)
            return f"{name}(UID{uid}) 首次获取粉丝数：{fans}"

        if fans > old_fanscount:
            await self.put_kv_data(str(uid), fans)
            return f"🌟 {name}(UID{uid}) 的粉丝数已从 {old_fanscount} 增加至 {fans}，上涨{fans - old_fanscount}个"
        if fans < old_fanscount:
            # （用到这个插件的UP平常应该不会执行到这条实现罢（
            await self.put_kv_data(str(uid), fans)
            return f"{name}(UID{uid}) 的粉丝数已从 {old_fanscount} 变为 {fans}，下降{old_fanscount - fans}个"
        #  fans == old_fanscount
        await self.put_kv_data(str(uid), fans)
        return f"⏳ {name}(UID{uid}) 的粉丝数为 {fans}，较上一次检查，未发生变化。"

    @filter.command_group("bwatch")
    def bwatch(self):
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bwatch.command("add", alias={"添加"})
    async def add(self, event: AstrMessageEvent, uid: str, time: str, ifequal: str):
        """
        添加UP
            请以 bwatch add [uid] [time] [ifequal] 格式发送
            Args:
                uid (str): UP主的UID
                time (str): 检查间隔时间（分钟）
                ifequal (str): 相等时是否推送（仅支持 true/false）
        """
        if not uid.isdigit() or not time.isdigit():
            yield event.plain_result(
                "请输入纯整数数字UID/时间。传入UID时不要带“UID”的前缀。"
            )
            event.stop_event()
            return
        if ifequal not in ["true", "false"]:
            yield event.plain_result(
                "“相等时是否推送” 参数应使用小写布尔值，仅传入 true(是) 或者 false(否)。"
            )
            event.stop_event()
            return
        uid_int = int(uid)
        time_int = int(time)
        self.config["uplist"].append(
            {
                "uid": uid_int,
                "time": time_int,
                "ifequal": ifequal,
                "umo": get_original_umo(event),
            }
        )
        self.config.save_config()
        logger.info("添加后尝试重新载入任务")
        for task in self.running_tasks:
            task.cancel()
        self.runtask.cancel()
        try:
            await self.runtask  # 等待任务完全取消
        except asyncio.CancelledError:
            pass
        self.runtask = asyncio.create_task(self.task_run())

        ifequal_text = "是" if ifequal == "true" else "否"
        yield event.plain_result(
            f"添加成功。请检查添加的配置：\n\nUID：{uid_int}\n\n检查间隔：{time}（分钟）\n\n相等时是否推送：{ifequal_text}"
        )
        event.stop_event()
        return

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bwatch.command("del", alias={"rm", "remove", "delete", "删除"})
    async def delete(self, event: AstrMessageEvent, uid: str):
        """删除UP
        Args:
            uid (str): UP主的UID
        """
        if not uid.isdigit():
            yield event.plain_result("请输入纯数字UID，传入UID时不要带“UID”的前缀。")
            event.stop_event()
            return
        uid_int = int(uid)
        if not any(
            d.get("uid") == uid_int and d.get("umo") == get_original_umo(event)
            for d in self.config["uplist"]
        ):
            yield event.plain_result("该UID不存在于监控列表中。")
            event.stop_event()
            return
        self.config["uplist"] = [
            i
            for i in self.config["uplist"]
            if i["uid"] != uid_int or i["umo"] != get_original_umo(event)
        ]
        self.config.save_config()
        logger.info("删除后尝试重新载入任务")
        for task in self.running_tasks:
            task.cancel()
        self.runtask.cancel()
        try:
            await self.runtask  # 等待任务完全取消
        except asyncio.CancelledError:
            pass
        self.runtask = asyncio.create_task(self.task_run())
        yield event.plain_result("删除成功。")
        event.stop_event()
        return

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bwatch.command("set", alias={"change", "setting","设置", "修改", "重设", "变更"})
    async def set(self, event: AstrMessageEvent, uid: str, time: str, ifequal: str):
        """
        设置UP
            请以 bwatch set [uid] [time] [ifequal] 命令发送
            Args:
                uid (str): UP主的UID
                time (str): 检查间隔时间（分钟）
                ifequal (str): 相等时是否推送（仅支持 true/false）
        """
        if not uid.isdigit() or not time.isdigit():
            yield event.plain_result(
                "请输入纯整数数字UID/时间。传入UID时不要带“UID”的前缀。"
            )
            event.stop_event()
            return
        if ifequal not in ["true", "false"]:
            yield event.plain_result(
                "“相等时是否推送” 参数应使用小写布尔值，仅传入 true(是) 或者 false(否)。"
            )
            event.stop_event()
            return
        uid_int = int(uid)
        time_int = int(time)
        if not any(
            d.get("uid") == uid_int and d.get("umo") == get_original_umo(event)
            for d in self.config["uplist"]
        ):
            yield event.plain_result("该UID不存在于监控列表中。")
            event.stop_event()
            return
        self.config["uplist"] = [
            i
            if i["uid"] != uid_int or i["umo"] != get_original_umo(event)
            else {
                "uid": uid_int,
                "time": time_int,
                "ifequal": ifequal,
                "umo": get_original_umo(event),
            }
            for i in self.config["uplist"]
        ]
        self.config.save_config()
        logger.info("修改后尝试重新载入任务")
        for task in self.running_tasks:
            task.cancel()
        self.runtask.cancel()
        try:
            await self.runtask  # 等待任务完全取消
        except asyncio.CancelledError:
            pass
        self.runtask = asyncio.create_task(self.task_run())
        ifequal_text = "是" if ifequal == "true" else "否"
        yield event.plain_result(
            f"修改成功。请检查修改后的配置：\n\nUID：{uid_int}\n\n检查间隔：{time}（分钟）\n\n相等时是否推送：{ifequal_text}"
        )
        event.stop_event()
        return

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bwatch.command("list", alias={"ls", "列出"})
    async def list(self, event: AstrMessageEvent):
        """列出所有UP"""
        # 只获取当前用户的监控项
        current_user_items = [
            item
            for item in self.config["uplist"]
            if item["umo"] == get_original_umo(event)
        ]

        if len(current_user_items) == 0:
            yield event.plain_result("没有添加任何监控对象。")
            event.stop_event()
            return

        yield event.plain_result(
            "检查列表：\n"
            + "\n".join(
                f"UID：{item['uid']}，检查间隔：{item['time']}（分钟），相等时是否推送：{'是' if item['ifequal'] == 'true' else '否'}"
                for item in current_user_items
            )
        )
        event.stop_event()
        return

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bwatch.command("test", alias={"check", "测试", "检查"})
    async def test(self, event: AstrMessageEvent):
        """获取并发送一次监控结果以测试"""
        found = False
        for i in self.config["uplist"]:
            if i["umo"] != get_original_umo(event):
                continue
            found = True
            send_message = await self.fans_compare(i["uid"])
            yield event.plain_result(send_message)

        if not found:
            yield event.plain_result("当前会话没有添加任何监控对象。")
        event.stop_event()
        return

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        for task in self.running_tasks:
            task.cancel()
        self.runtask.cancel()
        await self.session.close()
        logger.info("已取消所有任务。")
