import json
from typing import Any, Optional

from gluon_meson_sdk.dbs.milvus.milvus_for_langchain import MilvusForLangchain
from gluon_meson_sdk.models.chat_model import ChatModel
from gluon_meson_sdk.models.embedding_model import EmbeddingModel
from langchain.schema import Document
from loguru import logger
from pymilvus import FieldSchema, DataType

from nlu.base import IntentClassifier
from nlu.intent_config import IntentListConfig
from nlu.intent_with_entity import Intent
from nlu.llm.intent_call import IntentCall
from nlu.llm.intent_choosing_confirmer import IntentChoosingConfirmer
from nlu.llm.same_topic_checker import SameTopicChecker
from prompt_manager.base import PromptManager
from third_system.search_entity import SearchResponse, SearchParam, SearchParamFilter
from third_system.unified_search import UnifiedSearch
from tracker.context import ConversationContext

# should extract to a config file
system_template = """
你是一个聊天机器人，你需要对用户的意图进行识别，必须选择一个你认为最合适的意图，然后将其返回给我，不要返回多余的信息。

## 意图的可选项如下：
{intent_list}

## 下面是一些示例：
{examples}

## 问题：
消息：{question}
意图：
"""

system_template_without_example = """
你是一个聊天机器人，你需要结合上下文对用户的意图进行识别，必须选择一个你认为最合适的意图，然后将其返回给我，不要返回多余的信息。

## 意图的可选项如下：
{intent_list}
"""

topic = "hsbc_topic_for_intent"


class IntentConfig:
    def __init__(self, name, examples, slots):
        self.name = name
        self.examples = examples
        self.slots = slots


def get_intent_examples(user_input: str, parent_intent: str = None) -> list[dict[str, Any]]:
    unified_search_client = UnifiedSearch()
    filters = []
    if parent_intent:
        search_filter = SearchParamFilter(field="meta__full_parent_intent", op="like", value=[f"{parent_intent}%"])
        filters.append(search_filter)

    response: SearchResponse = unified_search_client.vector_search(
        search_param=SearchParam(query=user_input, filters=filters, size=3), table=topic
    )[0]

    intents_examples = extract_examples_from_response_text(response)
    return intents_examples


def process_one_intent_example(intent_example):
    text = intent_example.model_extra["text"]
    intent = intent_example.meta__reference.model_extra["meta__intent_result"]
    parent_intent = intent_example.meta__reference.model_extra["meta__full_parent_intent"]
    example = text
    score = intent_example.meta__score
    return dict(intent=intent, parent_intent=parent_intent, example=example, score=score)


def extract_examples_from_response_text(response: SearchResponse):
    return [process_one_intent_example(item) for item in response.items]


class LLMIntentClassifier(IntentClassifier):
    def __init__(
        self,
        chat_model: ChatModel,
        embedding_model: EmbeddingModel,
        milvus_for_langchain: MilvusForLangchain,
        intent_list_config: IntentListConfig,
        model_type: str,
        prompt_manager: PromptManager,
    ):
        self.model = chat_model
        self.embedding = embedding_model
        self.milvus_for_langchain = milvus_for_langchain
        self.retrieval_counts = 4
        self.embedding_type = "BASE_CH_P"
        self.model_type = model_type
        self.intent_list_config = intent_list_config
        self.prompt_manager = prompt_manager
        self.system_template_without_example = prompt_manager.load(name="intent_classification")
        self.intent_call = IntentCall(
            intent_list_config,
            prompt_manager.load(name="intent_classification_v2"),
            chat_model,
            model_type,
        )
        self.intent_choosing_confirmer = IntentChoosingConfirmer(
            prompt_manager.load(name="intent_choosing_confirm").template
        )
        self.same_topic_checker = SameTopicChecker()

    def train(self):
        # recreate topic
        # save all intent to milvus
        self.milvus_for_langchain.recreate_topic(
            topic,
            embedding_type=self.embedding_type,
            extra_meta_fields=[FieldSchema("intent", DataType.VARCHAR, max_length=256)],
            max_length=1024,
        )
        intent_examples = self.intent_list_config.get_intent_and_examples()
        docs = []
        for intent_example in intent_examples:
            intent = intent_example["intent"]
            examples = intent_example["examples"]
            for example in examples:
                doc = Document(
                    page_content=example,
                    metadata={"intent": intent, "source": "user upload"},
                )
                docs.append(doc)
        self.milvus_for_langchain.add_documents(topic, docs, embedding_type=self.embedding_type)

    def get_intent_by_parent(self, intent_example, parent_intent):
        if intent_example["parent_intent"] == parent_intent:
            return json.loads(intent_example["intent"])["intent"]
        else:
            example_parent_intent = intent_example["parent_intent"]
            if parent_intent:
                return example_parent_intent[:(len(parent_intent)+1)].split(".")[0]
            else:
                return example_parent_intent.split(".")[0]


    @classmethod
    def get_same_intent(cls, examples) -> Optional[str]:
        if len(examples) == 0:
            return None
        intents = [json.loads(example["intent"])["intent"] for example in examples]
        if all(intent == intents[0] for intent in intents):
            return intents[0]
        return None

    def classify_intent_overall(self, conversation: ConversationContext) -> Optional[Intent]:
        # intent confuse confirm
        if conversation.is_confused_with_intents():
            intent = self.intent_choosing_confirmer.confirm(conversation, conversation.session_id)
            conversation.confused_intents_resolved()
            if intent:
                logger.info(f"session {conversation.session_id}, intent: {intent}")
                description = self.intent_list_config.get_intent(intent).description
                return Intent(name=intent, confidence=1.0, description=description), None

        # same topic check
        chat_history = conversation.get_history().format_messages()
        previous_intent = conversation.current_intent

        if len(chat_history) > 1:
            start_new_topic, new_request = self.same_topic_checker.check_same_topic(chat_history, conversation.session_id)
            if previous_intent and not start_new_topic:
                return previous_intent

        is_final_intent = False
        current_intent = None
        middle_layer_intent = None
        while not is_final_intent:
            current_intent, unique_intent_from_examples = self.classify_intent(conversation, middle_layer_intent)
            # intent confuse check
            if current_intent and unique_intent_from_examples and current_intent.name != unique_intent_from_examples.name:
                conversation.set_confused_intents([current_intent, unique_intent_from_examples])
                break
            if current_intent and self.intent_list_config.get_intent(current_intent.name).has_children:
                is_final_intent = False
                middle_layer_intent = current_intent
            else:
                is_final_intent = True
        return current_intent

    def classify_intent(self, conversation: ConversationContext, parent_intent: Intent = None) -> tuple[Optional[Intent], Optional[Intent]]:
        user_input = conversation.current_user_input
        parent_intent_name = None
        if parent_intent:
            parent_intent_name = f"{parent_intent.parent_intent}.{parent_intent.name}" if parent_intent.parent_intent else parent_intent.name
        intent_name_list = self.intent_list_config.get_intent_name(parent_intent_name)
        intent_examples = get_intent_examples(user_input, parent_intent_name)
        for intent_example in intent_examples:
            intent_result = json.loads(intent_example["intent"])
            intent_name = self.get_intent_by_parent(intent_example, parent_intent_name)
            intent_result["intent"] = intent_name
            intent_example["intent"] = json.dumps(intent_result)
        unique_intent_in_examples = self.get_same_intent(intent_examples)
        if unique_intent_in_examples:
            unique_intent_in_examples = self.intent_list_config.get_intent(unique_intent_in_examples)
            unique_intent_in_examples = Intent(
                name=unique_intent_in_examples.name,
                confidence=1.0,
                description=unique_intent_in_examples.description,
            )
        intent = self.intent_call.classify_intent(
            user_input, intent_examples, conversation.session_id, parent_intent_name
        )

        if intent.intent in intent_name_list:
            logger.info(f"session {conversation.session_id}, intent: {intent.intent}")
            intent_config = self.intent_list_config.get_intent(intent.intent)
            return Intent(
                name=intent.intent, confidence=intent.confidence, description=intent_config.description,
                parent_intent=intent_config.parent_intent
            ), unique_intent_in_examples

        logger.info(f"intent: {intent.intent} is not predefined")
        return None, unique_intent_in_examples
