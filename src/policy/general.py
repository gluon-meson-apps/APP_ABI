from typing import Tuple, Optional

from action.base import Action
from action.actions.general import (
    EndDialogueAction,
    IntentConfirmAction,
    IntentFillingAction,
    AskForIntentChoosingAction,
)
from action.actions.bnb import BankRelatedAction, JumpOut
from action.repository.action_repository import ActionRepository, action_repository as default_action_repository
from policy.base import Policy
from tracker.context import ConversationContext
from loguru import logger
from nlu.forms import FormStore
from nlu.intent_with_entity import IntentWithEntity
from prompt_manager.base import PromptManager
from output_adapter.base import BaseOutputAdapter

INTENT_SIG_TRH = 0.8
SLOT_SIG_TRH = 0.8

MAX_FOLLOW_UP_TIMES = 2

IN_SCOPE_INTENTS = ["activate_function", "add_header", "enlarge_page", "reduce_page", "page_resize", "remove_header"]


def intent_in_scope(intent: str) -> bool:
    return True


class EndDialoguePolicy(Policy):
    def __init__(self, prompt_manager: PromptManager, form_store: FormStore):
        Policy.__init__(self, prompt_manager)

    def handle(self, IE: IntentWithEntity, context: ConversationContext) -> Tuple[bool, Action]:
        logger.info(f"Inquiry_times: {context.inquiry_times}")
        # 追问次数超过最大值
        if context.inquiry_times >= MAX_FOLLOW_UP_TIMES and context.current_intent is None:
            return True, EndDialogueAction()

        if context.current_intent is not None:
            if context.inquiry_times >= MAX_FOLLOW_UP_TIMES and not intent_in_scope(context.current_intent.name):
                return True, EndDialogueAction()
        return False, None


class IntentChoosingPolicy(Policy):
    def __init__(self, prompt_manager: PromptManager):
        Policy.__init__(self, prompt_manager)

    def handle(self, IE: IntentWithEntity, context: ConversationContext) -> Tuple[bool, Optional[Action]]:
        if context.is_confused_with_intents():
            return True, AskForIntentChoosingAction(prompt_manager=self.prompt_manager)
        return False, None


class JumpOutPolicy(Policy):
    def __init__(self, prompt_manager: PromptManager, form_store: FormStore):
        Policy.__init__(self, prompt_manager)

    def handle(self, IE: IntentWithEntity, context: ConversationContext) -> Tuple[bool, Optional[Action]]:
        # 没有意图
        if not IE.intent:
            return False, None

        # 非Agent处理之意图
        if IE.intent.name in ("skill_irrelevant", "other_skills"):
            return True, JumpOut()

        # 处理闲聊意图
        return False, None


class IntentFillingPolicy(Policy):
    def __init__(self, prompt_manager: PromptManager, form_store: FormStore):
        Policy.__init__(self, prompt_manager)
        self.form_store = form_store

    def handle(self, IE: IntentWithEntity, context: ConversationContext) -> Tuple[bool, Optional[Action]]:
        possible_slots = self.get_possible_slots(intent=IE)
        logger.debug(
            f"current status\nintent to clarify：{IE.intent}\n"
            f"entities：{[f'{slot.name}: {slot.value}' for slot in possible_slots if slot]}"
        )

        # 没有非辅助外的意图
        if IE.intent is None:
            context.set_state("intent_filling")
            return True, IntentFillingAction(prompt_manager=self.prompt_manager, form_store=self.form_store)

        # 有非辅助外的意图但是置信度低
        if (
            IE.intent.confidence < INTENT_SIG_TRH
            and intent_in_scope(IE.intent.name)
            and context.inquiry_times < MAX_FOLLOW_UP_TIMES
        ):
            context.set_state("intent_confirm")
            return True, IntentConfirmAction(IE.intent, prompt_manager=self.prompt_manager)
        return False, None


class AssistantPolicy(Policy):
    def __init__(
        self,
        prompt_manager: PromptManager,
        form_store: FormStore,
        action_repository: ActionRepository = default_action_repository,
    ):
        Policy.__init__(self, prompt_manager)
        self.form_store = form_store
        self.action_repository = action_repository

    def handle(self, IE: IntentWithEntity, context: ConversationContext) -> Tuple[bool, Optional[Action]]:
        potential_slots = self.get_possible_slots(intent=IE)
        logger.debug(
            f"final:\nintent：{IE.intent.name}\n"
            f"entities：{[f'{slot.name}: {slot.value}' for slot in potential_slots if slot]}"
        )
        intent_form = self.form_store.get_form_from_intent(IE.intent)

        # 出现了预定义之外的意图
        if not intent_form:
            return True, JumpOut()

        action = self.action_repository.find_by_name(intent_form.action)
        # 范围内意图但多轮追问都不能获取到必要的槽位
        if (
            intent_in_scope(IE.intent.name)
            and IE.intent.confidence > INTENT_SIG_TRH
            and context.inquiry_times >= MAX_FOLLOW_UP_TIMES
        ):
            if action is not None:
                return True, action
            return True, BankRelatedAction(intent_form.action, potential_slots, IE.intent, BaseOutputAdapter())

        # 范围内意图但多轮追问都不能获取到必要的槽位
        if (
            intent_in_scope(IE.intent.name)
            and IE.intent.confidence <= INTENT_SIG_TRH
            and context.inquiry_times >= MAX_FOLLOW_UP_TIMES
        ):
            context.set_state("intent_confirm")
            return True, EndDialogueAction()

        # 范围内意图，且此轮槽位有更新或者是新的意图
        if intent_in_scope(IE.intent.name) and context.has_update:
            context.has_update = False
            if action is not None:
                return True, action
            return True, BankRelatedAction(intent_form.action, potential_slots, IE.intent, BaseOutputAdapter())

        # 范围内意图但无更新
        if intent_in_scope(IE.intent.name) and not context.has_update:
            context.set_state("intent_confirm")
            return True, IntentConfirmAction(IE.intent, prompt_manager=self.prompt_manager)

        context.set_state("intent_filling")
        return True, IntentFillingAction(prompt_manager=self.prompt_manager, form_store=self.form_store)
