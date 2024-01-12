import json

from loguru import logger
from tabulate import tabulate

from action.base import Action, ActionResponse, ResponseMessageType, ChatResponseAnswer, GeneralResponse
from gluon_meson_sdk.models.scenario_model_registry.base import DefaultScenarioModelRegistryCenter
from third_system.search_entity import SearchParam
from third_system.unified_search import UnifiedSearch


prompt = """## Role
You are a helpful assistant, you need to answer the question from user based on below provided gps products

## attention
gps known as global payment system

## all gps products

{gps_products}

## user input

{user_input}

## INSTRUCT

now, answer the user's question in summary, and reply the final result with provided gps products
"""


class GPSProductCheckAction(Action):
    def __init__(self):
        self.unified_search = UnifiedSearch()
        self.scenario_model_registry = DefaultScenarioModelRegistryCenter()
        self.scenario_model = self.get_name() + "_action"

    def get_name(self) -> str:
        return "gps_product_check"

    def run(self, context) -> ActionResponse:
        logger.info(f"exec action: {self.get_name()} ")
        chat_model = self.scenario_model_registry.get_model(self.scenario_model)
        user_input = context.conversation.current_user_input

        response = self.unified_search.search(SearchParam(query=user_input, tags={"product_line": "gps_product"}))
        logger.info(f"search response: {response}")
        data = [item.json() for item in response[0].items]
        keys_to_exclude = ["meta__score", "meta__reference", "id", "seg_bb_rm", "seg_mme", "seg_lc", "seg_mc", "seg_fi",
                           "seg_nbfi", "seg_af", "seg_ps", "seg_rbb", "seg_gpb", "seg_bb_non_rm"]
        gps_products = ""
        if len(data) > 0:
            headers = (json.loads(data[0])).keys()
            headers = list(filter(lambda x: x not in keys_to_exclude, headers))
            pure_values = [
                {key: value for key, value in json.loads(item).items() if key not in keys_to_exclude}.values()
                for item in data
            ]
            gps_products = tabulate(pure_values, headers=headers)
            logger.info(f"headers: {gps_products}")

        final_prompt = prompt.format(gps_products=gps_products, user_input=user_input)
        result = chat_model.chat(final_prompt, max_length=2048).response
        logger.info(f"chat result: {result}")

        answer = ChatResponseAnswer(
            messageType=ResponseMessageType.FORMAT_TEXT, content=result, intent=context.conversation.current_intent.name
        )
        return GeneralResponse(code=200, message="success", answer=answer, jump_out_flag=False)