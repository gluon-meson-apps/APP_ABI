from typing import List, Dict, Union, Any, Tuple

from gluon_meson_sdk.dbs.milvus.milvus_connection import MilvusConnection
from gluon_meson_sdk.dbs.milvus.milvus_for_langchain import MilvusForLangchain
from gluon_meson_sdk.models.chat_model import ChatModel
from gluon_meson_sdk.models.embedding_model import EmbeddingModel
from langchain.schema import Document
from pymilvus import FieldSchema, DataType

from conversation_tracker.context import ConversationContext
from nlu.llm.context import FullLlmConversationContext
from nlu.intent_with_entity import Intent

from gm_logger import get_logger

logger = get_logger()

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
你是一个聊天机器人，你需要对用户的意图进行识别，必须选择一个你认为最合适的意图，然后将其返回给我，不要返回多余的信息。

## 意图的可选项如下：
{intent_list}
"""

topic = "test_topic_for_intent"

class IntentClassifier:
    def __init__(self, chat_model: ChatModel, embedding_model: EmbeddingModel, milvus_for_langchain: MilvusForLangchain):
        self.model = chat_model
        self.embedding = embedding_model
        self.milvus_for_langchain = milvus_for_langchain
        self.retrieval_counts = 4
        self.embedding_type = "E5"

    def train(self):
        # recreate topic
        # save all intent to milvus
        self.milvus_for_langchain.recreate_topic(
            topic, embedding_type=self.embedding_type,
            extra_meta_fields=[FieldSchema("intent", DataType.VARCHAR, max_length=256)],
            max_length=1024,
        )
        intent_examples = self.get_intent_examples_to_be_train()
        docs = []
        for intent_example in intent_examples:
            intent = intent_example["intent"]
            examples = intent_example["examples"]
            for example in examples:
                doc = Document(
                    page_content=example,
                    metadata={'intent': intent, 'source': 'user upload'}
                )
                docs.append(doc)
        self.milvus_for_langchain.add_documents(topic, docs, embedding_type=self.embedding_type)

    def get_intent_list(self):
        # should be extract to config file
        # return ["页面字体缩放", "增减表头的字段", "调整菜单的排序", "回单打印", "银企对账", "自助申请-开通功能",
        #         "系统设置-增加用户", "申请征信报告"]
        return ["控制智能家居", "问天气", "设置闹钟", "闲聊"]

    def get_intent_examples_to_be_train(self):
        # should be extract to config file
        return [
            {
                "intent": "控制智能家居",
                "examples": ['帮忙打开卧室的空调', '关灯', '打开电视', '关闭窗帘']
            },
            {
                "intent": "设置闹钟",
                "examples": ['明天早上六点叫我起床', '提醒我下午三点开会', '明天早上八点半叫我起床']
            },
            {
                "intent": "问天气",
                "examples": ['明天北京的天气怎么样', '今天上海的天气怎么样', '明天的天气怎么样']
            }
        ]

    def get_intent_examples(self, user_input: str) -> list[dict[str, Any]]:
        search_with_score = self.milvus_for_langchain.query_docs(topic, user_input, embedding_type=self.embedding_type,
                                                                 k=self.retrieval_counts)
        intents = []
        for result in search_with_score:
            example = result[0].page_content
            intent = result[0].metadata['intent']
            score = result[1]
            intents.append({
                "example": example,
                "intent": intent,
                "score": score
            })
        return intents

    def format_examples(self, examples: List[Dict[str, Any]]) -> str:
        template = """消息：{question}
意图：{intent}
"""
        return "\n".join([template.format(question=example["example"], intent=example["intent"]) for example in examples])

    def construct_message_with_few_shot_in_system_prompt(self, intent_list: List[str], examples: List[Dict[str, Any]], question: str) -> str:
        intent_list_str = "\n".join([f"- {intent}" for intent in intent_list])
        examples_str = self.format_examples(examples)
        system_message = system_template.format(intent_list=intent_list_str, examples=examples_str, question=question)
        logger.debug(system_message)
        intent = self.model.chat_single(system_message, model_type="cd-chatglm2-6b", max_length=1024)
        return intent

    def construct_message_with_few_shot_history(self, intent_list: List[str], examples: List[Dict[str, Any]], question: str) -> str:
        intent_list_str = "\n".join([f"- {intent}" for intent in intent_list])
        system_message = system_template_without_example.format(intent_list=intent_list_str)
        history = [('system', system_message)]
        user_template = """消息：{question}
意图："""
        for example in examples:
            history.append(('user', user_template.format(question=example['example'])))
            history.append(('assistant', example['intent']))

        intent = self.model.chat_single(user_template.format(question=question), history=history, model_type="qwen", max_length=1024)
        logger.debug(question)
        logger.debug(history)
        return intent.response


    def classify_intent(self, conversation_context: FullLlmConversationContext) -> Intent:
        user_input = conversation_context.get_current_user_input()
        intent_list = self.get_intent_list()
        question = user_input
        intent_examples = self.get_intent_examples(user_input)

        # intent_list_str = "\n".join([f"- {intent}" for intent in intent_list])
        # examples_str = self.format_examples(intent_examples)
        # system_message = system_template.format(intent_list=intent_list_str, examples=examples_str, question=question)
        # logger.debug(system_message)

        intent = self.construct_message_with_few_shot_history(intent_list, intent_examples, question)
        return Intent(name=intent, confidence=1.0)

if __name__ == '__main__':
    embedding_model = EmbeddingModel()
    classifier = IntentClassifier(ChatModel(), embedding_model, MilvusForLangchain(embedding_model, MilvusConnection()))
    # classifier.train()
    logger.debug(classifier.classify_intent(FullLlmConversationContext(ConversationContext("帮忙打开卧室的空调"))))