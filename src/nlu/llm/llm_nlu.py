from typing import Union

from loguru import logger
from tracker.context import ConversationContext
from nlu.base import Nlu
from nlu.intent_with_entity import IntentWithEntity
from nlu.llm.entity import LLMEntityExtractor
from nlu.llm.intent import LLMIntentClassifier


class LLMNlu(Nlu):
    def __init__(
        self,
        intent_classifier: LLMIntentClassifier,
        entity_extractor: LLMEntityExtractor,
    ):
        self.intent_classifier = intent_classifier
        self.entity_extractor = entity_extractor

    async def extract_intents_and_entities(self, conversation: ConversationContext) -> Union[IntentWithEntity, None]:
        conversation.set_status("intent_classifying")
        current_intent = self.intent_classifier.classify_intent(conversation)
        if current_intent is not None:
            conversation.current_intent = current_intent
            conversation.set_status("slot_filling")
            current_entities = await self.entity_extractor.extract_entity(conversation)
            entities_string = str(list(map(lambda entity: (entity.type, entity.value), current_entities)))
            logger.info("user %s, entities: %s", conversation.session_id, entities_string)
            return IntentWithEntity(intent=current_intent, entities=current_entities)
        else:
            return None
