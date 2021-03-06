#!/usr/bin/env python3

import asyncio
import aioamqp
import aiopg
import json
import uuid

from mnemosyne.config import config
from datetime import datetime

async def callback(channel, body, envelope, properties):
    decoded_blob = json.loads(body.decode("utf-8"))
    trace_uuid = decoded_blob["uuid"]
    transaction_uuid = decoded_blob["transaction"]
    origin_uuid = None if not decoded_blob[
        "origin"] else decoded_blob["origin"]
    start_time = datetime.fromtimestamp(decoded_blob["start"] / 1e9)
    end_time = datetime.fromtimestamp(decoded_blob["stop"] / 1e9)
    meta = json.dumps(decoded_blob["meta"])
    trace_name = decoded_blob["name"]
    spans = decoded_blob["span"]
    application = decoded_blob["application"]
    application_uuid = ""
    new_app = False
    app_is_name = False

    dsn = 'dbname=mnemosynetest1'
    async with aiopg.create_pool(dsn) as pool:
        async with pool.acquire() as conn:

            try:
                application_uuid = str(uuid.UUID(application, version=4))
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT uuid FROM applications WHERE uuid=%s",
                        (application_uuid))
                    ret = []
                    async for row in cur:
                        ret.append(row)
                    if len(ret) == 0:
                        new_app = True
            except ValueError:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT uuid FROM applications WHERE original_name=%s",
                        (application,))
                    ret = []
                    async for row in cur:
                        ret.append(row)
                    if len(ret) == 1:
                        application_uuid = ret[0][0]
                    else:
                        application_uuid = str(uuid.uuid4())
                        new_app = True
                        app_is_name = True

            if new_app:
                async with conn.cursor() as cur:
                    if app_is_name:
                        await cur.execute(
                            "INSERT INTO applications (uuid, name, original_name) VALUES (%s, %s, %s)",
                            (application_uuid, application, application))
                    else:
                        await cur.execute(
                            "INSERT INTO applications (uuid) VALUES (%s)",
                            (application_uuid,))

            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO traces (uuid, transaction_uuid, origin_uuid, start_time, end_time, meta, name, application_uuid) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (trace_uuid, transaction_uuid, origin_uuid, start_time, end_time, meta, trace_name, application_uuid))

                for span in spans:
                    await cur.execute(
                        "INSERT INTO spans (uuid, trace_uuid, name, start_time, end_time, meta) VALUES (%s, %s, %s, %s, %s, %s)",
                        (span["uuid"], trace_uuid, span["name"], datetime.fromtimestamp(span["start"] / 1e9), datetime.fromtimestamp(span["stop"] / 1e9), json.dumps(span["meta"])))

async def connect():
    uri = config.consumer.uri
    options = {}

    if uri.hostname is not None:
        options['hostname'] = uri.hostname

    if uri.port is not None:
        options['port'] = uri.port

    if uri.username is not None:
        options['login'] = uri.username

    if uri.password is not None:
        options['password'] = uri.password

    if uri.path is not None:
        options['virtualhost'] = uri.path

    if uri.scheme == 'amqps':
        options['ssl'] = True

    try:
        transport, protocol = await aioamqp.connect(**options)
        channel = await protocol.channel()

    except aioamqp.AmqpClosedConnection:
        print("Connection closed.")
        return

    queue_name = config.consumer.queue_name
    exchange_name = config.consumer.exchange_name

    await channel.exchange(exchange_name, "topic", durable=True)
    await channel.queue(queue_name=queue_name, durable=True)
    await channel.queue_bind(
        exchange_name=exchange_name, queue_name=queue_name, routing_key='#')

    print(' [*] Waiting for traces. To exit press CTRL+C')

    await channel.basic_consume(callback, queue_name=queue_name, no_ack=True)

    # # close using the `AMQP` protocol
    # await protocol.close()
    # # ensure the socket is closed.
    # transport.close()


def run():
    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(connect())
    event_loop.run_forever()
