import re

from gluon_meson_sdk.models.abstract_models.chat_message_preparation import ChatMessagePreparation
from loguru import logger

from action.base import ActionResponse, ResponseMessageType, ChatResponseAnswer, GeneralResponse
from action.actions.tb_guru.base import TBGuruAction
from action.context import ActionContext

prompt = """## Role
You are a helpful assistant, you need to answer the question from user based on the business resolution file.

## business resolution file content

{{br_file_content}}

## user input

{{user_input}}

"""


class BrFileQAAction(TBGuruAction):
    def __init__(self) -> None:
        super().__init__()

    def get_name(self) -> str:
        return "br_file_qa"

    async def run(self, context: ActionContext) -> ActionResponse:
        logger.info(f"exec action: {self.get_name()} ")

        first_file = await self.download_first_processed_file(context)
        if not first_file:
            return GeneralResponse.normal_failed_text_response(
                "No valid file uploaded, please upload a valid file and try again.",
                context.conversation.current_intent.name,
            )

        file_content = "\n".join([i.text for i in first_file.items])
        br_file_content = re.sub(r"\n+", "\n", file_content)

        chat_model = await self.scenario_model_registry.get_model(self.scenario_model, context.conversation.session_id)

        # get the url from entity

        chat_message_preparation = ChatMessagePreparation()
        chat_message_preparation.add_message(
            "user", prompt, br_file_content=br_file_content, user_input=context.conversation.current_user_input
        )
        chat_message_preparation.log(logger)

        result = (await chat_model.achat(**chat_message_preparation.to_chat_params(), max_length=2048)).response
        logger.info(f"chat result: {result}")

        answer = ChatResponseAnswer(
            messageType=ResponseMessageType.FORMAT_TEXT,
            content=result,
            intent=context.conversation.current_intent.name,
            references=first_file.items,
        )
        return GeneralResponse(code=200, message="success", answer=answer, jump_out_flag=False)
