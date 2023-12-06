import os
from typing import List
import gm_logger
from action.base import Action, ActionResponse
from llm.self_host import ChatModel
from nlu.intent_with_entity import Intent, Slot
from prompt_manager.base import PromptManager
from nlu.mlm.intent import IntentListConfig


logger = gm_logger.get_logger()


class SlotFillingAction(Action):
    """Slot filling action using large language models."""

    def __init__(self, slots: List[Slot], intent: Intent, prompt_manager: PromptManager):
        self.prompt_template = prompt_manager.load(name='action_slot_filling')
        self.llm = ChatModel()
        self.slots = slots
        self.intent = intent

    def run(self, context):
        context.set_status('action:slot_filling')
        # not_filled_slot = [k for k, v in slots.items() if v is None]
        prompt = self.prompt_template.format({
            "fill_slot": self.slots.pop().description,
            "intent": self.intent.name,
            "history": context.conversation.get_history().format_to_string(),
        })
        logger.debug(prompt)
        response = self.llm.chat(prompt, max_length=1024)
        return ActionResponse(text=response)
    


class IntentConfirmAction(Action):
    """Intent confirm action using large language models."""

    def __init__(self, intent: Intent, prompt_manager: PromptManager):
        self.prompt_template = prompt_manager.load(name='intent_confirm')
        self.llm = ChatModel()
        self.intent = intent
        pwd = os.path.dirname(os.path.abspath(__file__))
        intent_config_file_path = os.path.join(pwd, '../../', 'resources', 'scenes')
        self.intent_list_config = IntentListConfig.from_scenes(intent_config_file_path)

    def run(self, context):
        context.set_status('action:intent_confirm')
        prompt = self.prompt_template.format({
            "intent": self.intent.description,
            "intent_candidates": self.intent_list_config.get_intent_list(),
            "history": context.conversation.get_history().format_to_string(),
        })
        logger.debug(prompt)
        response = self.llm.chat(prompt, max_length=256)
        return ActionResponse(text=response)
    

class IntentFillingAction(Action):
    """Intent filling action using large language models."""

    def __init__(self, prompt_manager: PromptManager):
        self.prompt_template = prompt_manager.load(name='intent_filling')
        self.llm = ChatModel()

    def run(self, context):
        context.set_status('action:intent_filling')

        prompt = self.prompt_template.format({
            "history": context.conversation.get_history().format_to_string(),
        })
        logger.debug(prompt)
        response = self.llm.chat(prompt, max_length=256)
        return ActionResponse(text=response)

class FixedAnswerAction(Action):
    """Fixed response action giving pre-defined answers."""

    PresetResponses = {
        "评价": "请对我的服务进行评价,谢谢!",
        "打招呼": "您好,请问有什么可以帮助您的吗?",
        "结束对话": "再见,祝您生活愉快!"
    }

    def __init__(self, response_policy):
        self.response = self.PresetResponses.get(response_policy)

    def run(self, context):
        context.set_status('action:fixed_response')
        return self.response


class ChitChatAction(Action):
    def __init__(self, model_type: str, chat_model: ChatModel, user_input):
        self.model_type = model_type
        self.chat_model = chat_model
        self.user_input = user_input
        self.default_template = "我不知道该怎么回答好了"

    def run(self, context) -> ActionResponse:
        context.set_status('action:chitchat')
        # todo: add history from context
        result = self.chat_model.chat_single(self.user_input, model_type=self.model_type, max_length=1000)
        if result.response is None:
            return ActionResponse(text=self.default_template)
        else:
            return ActionResponse(text=result.response)


class GreetAction(Action):
    """Chat action using large language models."""

    def __init__(self, prompt_name: str, model_type: str, prompt_manager: PromptManager, prompt_domain: str = None):
        self.greet_prompt_template = prompt_manager.load(domain=prompt_domain, name=prompt_name)
        self.model = model_type
        self.llm = ChatModel()

    def run(self, context):
        context.set_status('action:greet')
        if self.greet_prompt_template is None:
            return None
        prompt = self.greet_prompt_template.format({})
        response = self.llm.chat_single(prompt, model_type=self.model)
        return response.response