import pandas as pd
from gluon_meson_sdk.models.abstract_models.chat_message_preparation import ChatMessagePreparation
from loguru import logger

from action.base import ActionResponse, ResponseMessageType, ChatResponseAnswer, GeneralResponse
from action.actions.tb_guru.base import TBGuruAction
from third_system.search_entity import SearchParam

prompt = """## Role
You are a helpful assistant, you need to answer the question from user based on below provided gps products

## attention
gps known as global payment system

## all gps products

{{gps_products}}

## user input

{{user_input}}

## INSTRUCT

now, answer the user's question in summary, and reply the final result with provided gps products
"""


class GPSProductCheckAction(TBGuruAction):
    def __init__(self):
        super().__init__()

    def get_name(self) -> str:
        return "gps_product_check"

    async def run(self, context) -> ActionResponse:
        logger.info(f"exec action: {self.get_name()} ")
        chat_model = await self.scenario_model_registry.get_model(self.scenario_model, context.conversation.session_id)
        user_input = context.conversation.current_user_input

        response = await self.unified_search.search(
            SearchParam(query=user_input, tags={"product_line": "gps_product"}), context.conversation.session_id
        )
        logger.info(f"search response: {response}")
        if len(response) == 0 or response[0].is_empty():
            answer = ChatResponseAnswer(
                messageType=ResponseMessageType.FORMAT_TEXT,
                content="Sorry, I can't answer your question, since there is no GPS product found.",
                intent=context.conversation.current_intent.name,
            )
            return GeneralResponse(code=200, message="failed", answer=answer, jump_out_flag=False)
        data = [item.dict() for item in response[0].items]
        keys_to_exclude = [
            "meta__score",
            "meta__reference",
            "id",
        ]
        gsp_products = pd.DataFrame(data).drop(keys_to_exclude, axis=1)

        chat_message_preparation = ChatMessagePreparation()
        chat_message_preparation.add_message("user", prompt, gps_products=gsp_products.to_string(), user_input=user_input)
        chat_message_preparation.log(logger)

        result = (await chat_model.achat(**chat_message_preparation.to_chat_params(), max_length=2048)).response
        logger.info(f"chat result: {result}")

        answer = ChatResponseAnswer(
            messageType=ResponseMessageType.FORMAT_TEXT,
            content=result,
            intent=context.conversation.current_intent.name,
            references=response[0].items,
        )
        return GeneralResponse(code=200, message="success", answer=answer, jump_out_flag=False)
