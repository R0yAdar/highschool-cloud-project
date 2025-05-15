""" This module is used to determine which event loop to use 
    for the entire program (main_server connections + peewee-postgres database connection)."""

import asyncio 

try:
    import uvloop
    uvloop.install() # Won't Work Becuase I am on Windows.
except ImportError:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        LOOP = asyncio.get_running_loop()
    except RuntimeError:
        LOOP = asyncio.new_event_loop()
