import os
from urllib.request import Request

from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from dialog_manager.base import BaseDialogManager, DialogManagerFactory
from fastapi import FastAPI
from uvicorn import run
from pydantic import BaseModel

load_dotenv()

app = FastAPI()
dialog_manager: BaseDialogManager = DialogManagerFactory.create_dialog_manager()

if os.getenv("LOCAL_MODE") == '1':
    origins = [
        "http://127.0.0.1",
        "http://127.0.0.1:8089",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as err:
        err_msg = f"Error occurred: {err}"
        print(err_msg)
        return JSONResponse(status_code=500, content=err_msg)


class MessageInput(BaseModel):
    session_id: str
    user_input: str


@app.post("/chat/")
def chat(data: MessageInput):
    session_id = data.session_id
    user_input = data.user_input
    result, conversation = dialog_manager.handle_message(user_input, session_id)
    return {"response": result, "conversation": conversation, "session_id": conversation.session_id}


def main():
    if os.getenv("LOCAL_MODE") == '1':
        run("app:app", host="0.0.0.0", port=7788, reload=True,
            reload_dirs=os.path.dirname(os.path.abspath(__file__)))
    else:
        run("app:app", host="0.0.0.0", port=7788)


if __name__ == "__main__":
    # session_id = "123"
    # user_input = "列太少了不清楚"
    # result, conversation = dialog_manager.handle_message(user_input, session_id)
    main()
