"""Compatibility entry point for the single qualified production composition."""
from .launch import main,DIRECTORY
if __name__=='__main__':
    import asyncio
    asyncio.run(main())
