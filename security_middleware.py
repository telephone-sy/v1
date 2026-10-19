from starlette.responses import JSONResponse


class RequestBodyLimitMiddleware:
    def __init__(self, app, maximum_bytes: int):
        self.app = app
        self.maximum_bytes = maximum_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length:
            try:
                if int(length) > self.maximum_bytes:
                    await JSONResponse({"detail": "حجم الطلب كبير جداً"}, status_code=413)(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse({"detail": "ترويسة حجم الطلب غير صالحة"}, status_code=400)(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.maximum_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await JSONResponse({"detail": "حجم الطلب كبير جداً"}, status_code=413)(scope, receive, send)


class _RequestTooLarge(Exception):
    pass