import logging
import asyncio
import discord
from discord.ext import tasks

logger = logging.getLogger("discord")


class ConnectionMonitor:
    def __init__(self, bot, token: str):
        self.bot = bot
        self.token = token
        self.fail_count = 0
        self.is_reconnecting = False

    @tasks.loop(seconds=30)
    async def monitor_connection(self):
        if self.is_reconnecting:
            return

        latency = self.bot.latency

        if not self.bot.is_ready() or latency != latency or latency > 15:
            self.fail_count += 1
            logger.warning(f"Connection check failed ({self.fail_count}/2)")
            print(f"Connection check failed ({self.fail_count}/2)")
        else:
            self.fail_count = 0

        if self.fail_count >= 2:
            await self.reconnect_logic()

    async def reconnect_logic(self):
        self.is_reconnecting = True
        logger.error("Connection lost. Attempting manual reconnect...")
        print("Connection lost. Attempting manual reconnect...")

        while not self.bot.is_closed():
            try:
                await self.bot.close()
                await asyncio.sleep(2)

                await self.bot.login(self.token)
                await self.bot.connect()

                logger.info("Successfully reconnected to Discord Gateway.")
                print("Successfully reconnected to Discord Gateway.")

                self.fail_count = 0
                self.is_reconnecting = False
                break
            except Exception as e:
                logger.error(f"Reconnect failed: {e}. Retrying in 30s...")
                print(f"Reconnect failed: {e}. Retrying in 30s...")
                await asyncio.sleep(30)

    @monitor_connection.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()

    def start(self):
        self.monitor_connection.start()

    def stop(self):
        self.monitor_connection.stop()