import pathlib
p = pathlib.Path(r"C:\Users\Ramy\Documents\polymarket-crypto\backend\app\live\readonly_book_stream.py")
content = p.read_text("utf-8")

# Add _running guard to StreamBook.run()
old = """    async def run(self,*,connect_factory=None):
        from websockets.asyncio.client import connect
        class FixedConnect(connect):
            def process_redirect(self,exc):return exc
        try:
            async with (connect_factory or FixedConnect)(WS,ping_interval=None,open_timeout=10,close_timeout=2,max_size=4000000) as ws:"""

new = """    async def run(self,*,connect_factory=None):
        if getattr(self,"_ws_running",False):
            return
        self._ws_running=True
        from websockets.asyncio.client import connect
        class FixedConnect(connect):
            def process_redirect(self,exc):return exc
        try:
            async with (connect_factory or FixedConnect)(WS,ping_interval=None,open_timeout=10,close_timeout=2,max_size=4000000) as ws:"""

content = content.replace(old, new)

# Add _ws_running cleanup in disconnect
old2 = """    def disconnect(self):
        if self.connected:self.transition('DISCONNECTED')
        super().disconnect();self.depth={}"""
new2 = """    def disconnect(self):
        if self.connected:self.transition('DISCONNECTED')
        super().disconnect();self.depth={}
        self._ws_running=False"""
content = content.replace(old2, new2)

p.write_text(content, "utf-8")
print("Fixed")
compile(content, "readonly_book_stream.py", "exec")
print("SYNTAX_OK")
