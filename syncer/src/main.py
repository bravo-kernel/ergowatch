import os
import asyncio
import asyncpg
import time
import logging

from utils import prep_logger
import coingecko
import continuous
import snapshots

# Logger
logger = logging.getLogger("main")
prep_logger(logger, level=logging.INFO)


logger.info("Retrieving DB settings from environment")
try:
    DB_HOST = os.environ["DB_URL"]
    DB_NAME = os.environ["DB_NAME"]
    DB_USER = os.environ["DB_USER"]
    DB_PASS = os.environ["POSTGRES_PASSWORD"]
except KeyError as e:
    logger.error(f"Environment variable {e} is not set")
    exit(1)

DBSTR = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

# Node heights queue
Q = asyncio.Queue()

# Using a queue as some sort of mutex for our single db connection
C = asyncio.Queue()
DB_LOCK = asyncio.Lock()


def handle_notification(conn, pid, channel, payload):
    logger.info(f"Received notificatoin with payload: {payload}")
    Q.put_nowait(payload)
    logger.info(f"Queue size is now: {Q.qsize()}")


def process_queue():
    while Q.qsize() > 1:
        height = Q.get_nowait()
        logger.info(f"Skipping height: {height} - more recent one available")

    height = Q.get_nowait()
    conn = C.get_nowait()

    # Wait some to ensure chain-grabber is done
    time.sleep(2)

    async def refresh():
        try:
            try:
                await coingecko.sync(conn)
            except Exception as e:
                logger.error("Error while calling coingecko.sync()")
                logger.error(e)

            try:
                await conn.execute("CALL ew.sync($1);", int(height))
            except Exception as e:
                logger.error("Error while calling ew.sync()")
                logger.error(e)

            try:
                await continuous.sync(conn)
            except Exception as e:
                logger.error("Error while calling continuous.sync()")
                logger.error(e)

            try:
                await snapshots.sync(conn)
            except Exception as e:
                logger.error("Error while calling snapshots.sync()")
                logger.error(e)

            logger.info(f"Task for {height} completed")

        except Exception as e:
            logger.warning(e)

        finally:
            # "release" connection by putting it back in the queue
            C.put_nowait(conn)

    logger.info(f"Submitting task for {height}")
    asyncio.create_task(refresh())


async def make_connection():
    async with DB_LOCK:
        assert C.empty()
        logger.info(f"Connecting to database: {DB_USER}@{DB_HOST}/{DB_NAME}")
        conn = await asyncpg.connect(DBSTR)
        channel = "ergowatch"
        logger.info(f"Adding listener for channel '{channel}'")
        await conn.add_listener(channel, handle_notification)
        C.put_nowait(conn)


async def reset_connection():
    async with DB_LOCK:
        logger.info("Resetting db connection")
        assert not C.empty()
        conn = C.get_nowait()
        await conn.close()
    await make_connection()


async def main():
    await make_connection()
    connection_usage_counter = 0
    while True:
        # There is at least one new height to process
        # and db is done processing previous ones.
        if not Q.empty() and not C.empty():
            # Using same connection forever seems to leak memory.
            # Reset connection after x process_queue calls.
            connection_usage_counter += 1
            if connection_usage_counter >= 100:
                await reset_connection()
                connection_usage_counter = 0

            # Process only once connection reset is completed
            async with DB_LOCK:
                process_queue()

        await asyncio.sleep(10)

    logger.info("Closing db connection")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
